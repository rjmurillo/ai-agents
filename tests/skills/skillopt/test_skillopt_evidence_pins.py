"""Tests for the skillopt read-only pins and the proposer-tier check."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import skillopt
from skillopt_helpers import Capture, write_json

EVAL = {"splits": {"train": ["t1", "t2", "t3", "t4"], "sel": ["s1", "s2"]}, "tasks": {}}


class TestPins:
    def setup_files(self, tmp_path: Path) -> tuple[Path, Path]:
        eval_path = write_json(tmp_path / "eval.json", EVAL)
        verifier = tmp_path / "check.py"
        verifier.write_text("print('ok')\n", encoding="utf-8")
        return eval_path, verifier

    def pin(self, tmp_path: Path) -> Path:
        eval_path, verifier = self.setup_files(tmp_path)
        out = tmp_path / "pins.json"
        argv = [
            "pin",
            "--eval",
            str(eval_path),
            "--surface",
            f"verifier={verifier}",
            "--model",
            "claude-sonnet-5-5",
            "--out",
            str(out),
        ]
        assert skillopt.main(argv) == 0
        return out

    def test_match_exits_0(self, tmp_path: Path, capsys: Capture) -> None:
        pins = self.pin(tmp_path)
        assert skillopt.main(["pin-check", "--pins", str(pins)]) == 0
        assert json.loads(capsys.readouterr().out)["verdict"] == "MATCH"

    def test_changed_verifier_exits_1(self, tmp_path: Path, capsys: Capture) -> None:
        pins = self.pin(tmp_path)
        (tmp_path / "check.py").write_text("print('pass anyway')\n", encoding="utf-8")
        assert skillopt.main(["pin-check", "--pins", str(pins)]) == 1
        assert json.loads(capsys.readouterr().out)["changed_surfaces"] == ["verifier"]

    def test_model_swap_exits_1(self, tmp_path: Path, capsys: Capture) -> None:
        pins = self.pin(tmp_path)
        assert skillopt.main(["pin-check", "--pins", str(pins), "--model", "claude-opus-5-5"]) == 1
        assert json.loads(capsys.readouterr().out)["model_changed"] is True

    def test_missing_surface_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        eval_path, _ = self.setup_files(tmp_path)
        argv = [
            "pin",
            "--eval",
            str(eval_path),
            "--surface",
            f"tracer={tmp_path / 'nope'}",
            "--model",
            "m",
            "--out",
            str(tmp_path / "pins.json"),
        ]
        assert skillopt.main(argv) == 2
        assert "does not exist" in capsys.readouterr().err

    def test_bad_surface_syntax_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        eval_path, _ = self.setup_files(tmp_path)
        argv = [
            "pin",
            "--eval",
            str(eval_path),
            "--surface",
            "noequals",
            "--model",
            "m",
            "--out",
            str(tmp_path / "pins.json"),
        ]
        assert skillopt.main(argv) == 2
        assert "NAME=PATH" in capsys.readouterr().err

    def test_out_over_pinned_surface_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        eval_path, verifier = self.setup_files(tmp_path)
        argv = [
            "pin",
            "--eval",
            str(eval_path),
            "--surface",
            f"verifier={verifier}",
            "--model",
            "m",
            "--out",
            str(verifier),
        ]
        assert skillopt.main(argv) == 2
        assert "must not overwrite" in capsys.readouterr().err

    def test_out_inside_pinned_directory_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        eval_path, _ = self.setup_files(tmp_path)
        graders = tmp_path / "graders"
        graders.mkdir()
        (graders / "grade.py").write_text("x\n", encoding="utf-8")
        argv = ["pin", "--eval", str(eval_path), "--surface", f"tracer={graders}"]
        argv += ["--model", "m", "--out", str(graders / "pins.json")]
        assert skillopt.main(argv) == 2
        assert "sit inside a pinned surface" in capsys.readouterr().err
        assert not (graders / "pins.json").exists()

    def test_out_hard_linked_to_pinned_file_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        eval_path, verifier = self.setup_files(tmp_path)
        before = eval_path.read_bytes()
        alias = tmp_path / "pins.json"
        alias.hardlink_to(eval_path)
        argv = ["pin", "--eval", str(eval_path), "--surface", f"verifier={verifier}"]
        argv += ["--model", "m", "--out", str(alias)]
        assert skillopt.main(argv) == 2
        assert "hard link" in capsys.readouterr().err
        assert eval_path.read_bytes() == before

    @pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privilege on Windows")
    def test_retargeted_symlink_is_a_mismatch(self, tmp_path: Path, capsys: Capture) -> None:
        eval_path, _ = self.setup_files(tmp_path)
        v1, v2 = tmp_path / "check-v1.py", tmp_path / "check-v2.py"
        v1.write_text("same\n", encoding="utf-8")
        v2.write_text("same\n", encoding="utf-8")
        link = tmp_path / "current-check.py"
        link.symlink_to(v1)
        out = tmp_path / "pins.json"
        argv = ["pin", "--eval", str(eval_path), "--surface", f"verifier={link}"]
        assert skillopt.main([*argv, "--model", "m", "--out", str(out)]) == 0
        link.unlink()
        link.symlink_to(v2)
        assert skillopt.main(["pin-check", "--pins", str(out)]) == 1
        assert json.loads(capsys.readouterr().out)["changed_surfaces"] == ["verifier"]

    def test_pins_without_target_still_match(self, tmp_path: Path, capsys: Capture) -> None:
        pins = self.pin(tmp_path)
        data = json.loads(pins.read_text(encoding="utf-8"))
        for entry in data["surfaces"].values():
            entry.pop("target")
        pins.write_text(json.dumps(data), encoding="utf-8")
        assert skillopt.main(["pin-check", "--pins", str(pins)]) == 0
        assert json.loads(capsys.readouterr().out)["verdict"] == "MATCH"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits only")
    def test_pins_file_follows_umask(self, tmp_path: Path) -> None:
        pins = self.pin(tmp_path)
        probe = tmp_path / "probe"
        probe.write_text("x", encoding="utf-8")
        assert pins.stat().st_mode & 0o777 == probe.stat().st_mode & 0o777

    def test_duplicate_surface_name_exits_2(self, tmp_path: Path, capsys: Capture) -> None:
        eval_path, verifier = self.setup_files(tmp_path)
        other = tmp_path / "other.py"
        other.write_text("y\n", encoding="utf-8")
        argv = ["pin", "--eval", str(eval_path), "--surface", f"verifier={verifier}"]
        argv += ["--surface", f"verifier={other}", "--model", "m"]
        argv += ["--out", str(tmp_path / "pins.json")]
        assert skillopt.main(argv) == 2
        assert "given twice" in capsys.readouterr().err

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ('{"schema": "other/1", "surfaces": {}}', "schema"),
            ('{"schema": "skillopt-pins/1", "model": "m", "surfaces": {}}', "'eval' entry"),
            ("{not json", ""),
        ],
    )
    def test_malformed_pins_file_exits_2(
        self, tmp_path: Path, capsys: Capture, content: str, message: str
    ) -> None:
        pins = tmp_path / "pins.json"
        pins.write_text(content, encoding="utf-8")
        assert skillopt.main(["pin-check", "--pins", str(pins)]) == 2
        assert message in capsys.readouterr().err


class TestPairGateDeclaredPins:
    def gate_files(self, tmp_path: Path) -> list[str]:
        verifier = tmp_path / "check.py"
        verifier.write_text("v1\n", encoding="utf-8")
        eval_set = {"splits": {"sel": ["s1"]}, "pins": "pins.json"}
        eval_path = write_json(tmp_path / "eval.json", eval_set)
        assert (
            skillopt.main(
                [
                    "pin",
                    "--eval",
                    str(eval_path),
                    "--surface",
                    f"verifier={verifier}",
                    "--model",
                    "m",
                    "--out",
                    str(tmp_path / "pins.json"),
                ]
            )
            == 0
        )
        inc = write_json(tmp_path / "inc.json", {"s1": False})
        cand = write_json(tmp_path / "cand.json", {"s1": True})
        return [
            "pair-gate",
            "--eval",
            str(eval_path),
            "--incumbent-results",
            str(inc),
            "--candidate-results",
            str(cand),
        ]

    def test_unchanged_pins_gate_normally(self, tmp_path: Path, capsys: Capture) -> None:
        assert skillopt.main(self.gate_files(tmp_path)) == 0
        assert json.loads(capsys.readouterr().out)["verdict"] == "ACCEPT_PARETO"

    def test_changed_verifier_refuses_gate(self, tmp_path: Path, capsys: Capture) -> None:
        argv = self.gate_files(tmp_path)
        (tmp_path / "check.py").write_text("v2\n", encoding="utf-8")
        assert skillopt.main(argv) == 2
        assert "read-only surface changed" in capsys.readouterr().err

    def test_missing_pins_file_refuses_gate(self, tmp_path: Path, capsys: Capture) -> None:
        argv = self.gate_files(tmp_path)
        (tmp_path / "pins.json").unlink()
        assert skillopt.main(argv) == 2
        assert "does not exist" in capsys.readouterr().err

    def test_pins_for_another_eval_set_refuse_gate(self, tmp_path: Path, capsys: Capture) -> None:
        argv = self.gate_files(tmp_path)
        other = write_json(
            tmp_path / "eval-copy.json", {"splits": {"sel": ["s1"]}, "pins": "pins.json"}
        )
        argv[argv.index("--eval") + 1] = str(other)
        assert skillopt.main(argv) == 2
        assert "not the one being gated" in capsys.readouterr().err

    def test_changed_verifier_refuses_efficiency_gate(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        argv = self.gate_files(tmp_path)
        (tmp_path / "check.py").write_text("v2\n", encoding="utf-8")
        measurements = write_json(tmp_path / "measurements.json", {})
        argv = ["efficiency-gate", *argv[1:], "--measurements", str(measurements)]
        assert skillopt.main(argv) == 2
        assert "read-only surface changed" in capsys.readouterr().err

    def test_no_declaration_keeps_old_behavior(self, tmp_path: Path) -> None:
        eval_path = write_json(tmp_path / "eval.json", {"splits": {"sel": ["s1"]}})
        inc = write_json(tmp_path / "inc.json", {"s1": False})
        cand = write_json(tmp_path / "cand.json", {"s1": True})
        assert (
            skillopt.main(
                [
                    "pair-gate",
                    "--eval",
                    str(eval_path),
                    "--incumbent-results",
                    str(inc),
                    "--candidate-results",
                    str(cand),
                ]
            )
            == 0
        )


class TestProposerCheck:
    @pytest.mark.parametrize(
        ("model", "code", "word"),
        [
            ("claude-opus-5-5", 0, "CAPABLE"),
            ("claude-sonnet-5-5", 0, "CAPABLE"),
            ("gpt-5", 0, "CAPABLE"),
            ("gemini-2.5-pro", 0, "CAPABLE"),
            ("gemini-2.5-flash-lite", 1, "LIGHTWEIGHT"),
            ("claude-haiku-5-5", 1, "LIGHTWEIGHT"),
            ("gpt-3.5-turbo", 1, "LIGHTWEIGHT"),
            ("mixtral-8x7b", 1, "LIGHTWEIGHT"),
            ("gpt-4o-mini", 1, "LIGHTWEIGHT"),
            ("some-local-model", 1, "UNKNOWN"),
        ],
    )
    def test_tiers(self, capsys: Capture, model: str, code: int, word: str) -> None:
        assert skillopt.main(["proposer-check", "--model", model]) == code
        out = capsys.readouterr()
        assert out.out.strip() == word
        if code:
            assert "STOP" in out.err

    def test_blank_model_exits_2(self, capsys: Capture) -> None:
        assert skillopt.main(["proposer-check", "--model", "  "]) == 2
        assert "nonempty" in capsys.readouterr().err
