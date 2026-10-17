"""Tests for the skillopt apply CLI and its incumbent protection."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import skillopt
from skillopt_helpers import (
    Capture,
    valid_eval,
    write_json,
)


class TestApplyCli:
    @staticmethod
    def _setup(tmp_path: Path, patches: object | None = None) -> tuple[Path, Path]:
        skill = tmp_path / "SKILL.md"
        skill.write_bytes(b"a\nb")
        p = write_json(
            tmp_path / "p.json", [{"op": "append", "text": "c"}] if patches is None else patches
        )
        return skill, p

    def test_apply_writes_candidate_and_leaves_incumbent(self, tmp_path: Path) -> None:
        skill, patches = self._setup(tmp_path)
        out = tmp_path / "cand.md"
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
            "--out",
            str(out),
        ]
        assert skillopt.main(argv) == 0
        assert out.read_bytes() == b"a\nb\nc"
        assert skill.read_bytes() == b"a\nb"

    def test_apply_refuses_same_path(self, tmp_path: Path, capsys: Capture) -> None:
        skill, patches = self._setup(tmp_path)
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
            "--out",
            str(skill),
        ]
        assert skillopt.main(argv) == 2
        assert (
            "refusing to overwrite the incumbent; write the candidate to a separate --out path"
            in (capsys.readouterr().err)
        )
        assert skill.read_bytes() == b"a\nb"

    def test_apply_refuses_other_spelling_of_same_path(self, tmp_path: Path) -> None:
        skill, patches = self._setup(tmp_path)
        (tmp_path / "sub").mkdir()
        alias = tmp_path / "sub" / ".." / "SKILL.md"
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
            "--out",
            str(alias),
        ]
        assert skillopt.main(argv) == 2
        assert skill.read_bytes() == b"a\nb"

    def test_apply_refuses_symlink_to_incumbent(self, tmp_path: Path) -> None:
        skill, patches = self._setup(tmp_path)
        link = tmp_path / "link.md"
        try:
            link.symlink_to(skill)
        except OSError:  # pragma: no cover - symlinks unavailable
            pytest.skip("symlinks unavailable")
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
            "--out",
            str(link),
        ]
        assert skillopt.main(argv) == 2
        assert skill.read_bytes() == b"a\nb"

    def test_apply_refuses_hardlink_to_incumbent(self, tmp_path: Path) -> None:
        skill, patches = self._setup(tmp_path)
        hard = tmp_path / "hard.md"
        try:
            os.link(skill, hard)
        except OSError:  # pragma: no cover - hard links unavailable
            pytest.skip("hard links unavailable")
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
            "--out",
            str(hard),
        ]
        assert skillopt.main(argv) == 2
        assert skill.read_bytes() == b"a\nb"
        assert hard.read_bytes() == b"a\nb"

    def test_apply_without_out_errors(self, tmp_path: Path, capsys: Capture) -> None:
        skill, patches = self._setup(tmp_path)
        assert (
            skillopt.main(
                [
                    "apply",
                    "--eval",
                    str(valid_eval(tmp_path)),
                    "--skill",
                    str(skill),
                    "--patches",
                    str(patches),
                    "--budget",
                    "1",
                ]
            )
            == 2
        )
        assert "requires --out" in capsys.readouterr().err
        assert skill.read_bytes() == b"a\nb"

    def test_dry_run_without_out_ok_and_writes_nothing(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        skill, patches = self._setup(tmp_path)
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
            "--dry-run",
        ]
        assert skillopt.main(argv) == 0
        assert "apply cleanly" in capsys.readouterr().err
        assert skill.read_bytes() == b"a\nb"
        assert sorted(p.name for p in tmp_path.iterdir()) == ["SKILL.md", "evals", "p.json"]

    def test_dry_run_with_out_does_not_write(self, tmp_path: Path) -> None:
        skill, patches = self._setup(tmp_path)
        out = tmp_path / "o.md"
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
            "--dry-run",
            "--out",
            str(out),
        ]
        assert skillopt.main(argv) == 0
        assert not out.exists()

    def test_budget_overflow_exit_two_incumbent_unchanged(self, tmp_path: Path) -> None:
        skill, patches = self._setup(
            tmp_path, [{"op": "append", "text": "x"}, {"op": "append", "text": "y"}]
        )
        out = tmp_path / "o.md"
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
            "--out",
            str(out),
        ]
        assert skillopt.main(argv) == 2
        assert skill.read_bytes() == b"a\nb"
        assert not out.exists()

    @pytest.mark.parametrize(
        ("patches", "message"),
        [
            ([{"op": "delete", "anchor": "zzz"}], "anchor not found"),
            ([{"op": "delete", "anchor": "a"}, {"op": "delete", "anchor": "a"}], "budget exceeded"),
            ([{"op": "nope"}], "invalid op"),
            ({"op": "append"}, "list of objects"),
            (["append"], "list of objects"),
        ],
    )
    def test_bad_patches_exit_two(
        self, tmp_path: Path, capsys: Capture, patches: object, message: str
    ) -> None:
        skill, p = self._setup(tmp_path, patches)
        out = tmp_path / "o.md"
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(p),
            "--budget",
            "1",
            "--out",
            str(out),
        ]
        assert skillopt.main(argv) == 2
        assert message in capsys.readouterr().err
        assert skill.read_bytes() == b"a\nb"

    def test_ambiguous_anchor_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        skill = tmp_path / "S.md"
        skill.write_bytes(b"dup\ndup")
        p = write_json(tmp_path / "p.json", [{"op": "delete", "anchor": "dup"}])
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(p),
            "--budget",
            "1",
            "--out",
            str(tmp_path / "o"),
        ]
        assert skillopt.main(argv) == 2
        assert "ambiguous" in capsys.readouterr().err
        assert skill.read_bytes() == b"dup\ndup"

    def test_missing_skill_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        p = write_json(tmp_path / "p.json", [])
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(tmp_path / "gone.md"),
            "--patches",
            str(p),
            "--budget",
            "1",
            "--out",
            str(tmp_path / "o"),
        ]
        assert skillopt.main(argv) == 2
        assert "gone.md" in capsys.readouterr().err

    def test_invalid_patches_json_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        skill, p = self._setup(tmp_path)
        p.write_text("[", encoding="utf-8")
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(p),
            "--budget",
            "1",
            "--out",
            str(tmp_path / "o"),
        ]
        assert skillopt.main(argv) == 2
        assert capsys.readouterr().err.startswith("skillopt: ")

    def test_crlf_file_round_trips_through_cli(self, tmp_path: Path) -> None:
        skill = tmp_path / "S.md"
        skill.write_bytes(b"one\r\ntwo\r\n")
        p = write_json(tmp_path / "p.json", [{"op": "replace", "anchor": "two", "text": "TWO"}])
        out = tmp_path / "o.md"
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(p),
            "--budget",
            "1",
            "--out",
            str(out),
        ]
        assert skillopt.main(argv) == 0
        assert out.read_bytes() == b"one\r\nTWO\r\n"
        assert skill.read_bytes() == b"one\r\ntwo\r\n"

    def test_unpatched_crlf_copy_is_byte_identical(self, tmp_path: Path) -> None:
        skill = tmp_path / "S.md"
        skill.write_bytes(b"one\r\ntwo\r\n")
        p = write_json(tmp_path / "p.json", [])
        out = tmp_path / "o.md"
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(p),
            "--budget",
            "0",
            "--out",
            str(out),
        ]
        assert skillopt.main(argv) == 0
        assert skillopt.file_sha256(out) == skillopt.file_sha256(skill)

    def test_missing_eval_arg_is_a_usage_error(self, tmp_path: Path) -> None:
        skill, patches = self._setup(tmp_path)
        out = tmp_path / "o.md"
        argv = ["apply", "--skill", str(skill), "--patches", str(patches)]
        argv += ["--budget", "1", "--out", str(out)]
        with pytest.raises(SystemExit) as exc:
            skillopt.main(argv)
        assert exc.value.code == 2
        assert not out.exists()

    @pytest.mark.parametrize(
        ("eval_doc", "message"),
        [
            ({"splits": {"sel": []}}, "vacuous"),
            ({"splits": {"dev": ["a"]}}, "no 'sel' split"),
            ({}, "no 'sel' split"),
            ([], "apply eval input must be a JSON object"),
        ],
    )
    def test_bad_sel_split_exits_two_and_writes_nothing(
        self, tmp_path: Path, capsys: Capture, eval_doc: object, message: str
    ) -> None:
        skill, patches = self._setup(tmp_path)
        ev = write_json(tmp_path / "bad_eval.json", eval_doc)
        out = tmp_path / "o.md"
        argv = ["apply", "--eval", str(ev), "--skill", str(skill)]
        argv += ["--patches", str(patches), "--budget", "1", "--out", str(out)]
        assert skillopt.main(argv) == 2
        assert message in capsys.readouterr().err
        assert not out.exists()
        assert skill.read_bytes() == b"a\nb"

    def test_missing_eval_file_exits_two(self, tmp_path: Path) -> None:
        skill, patches = self._setup(tmp_path)
        argv = ["apply", "--eval", str(tmp_path / "gone.json"), "--skill", str(skill)]
        argv += ["--patches", str(patches), "--budget", "1", "--dry-run"]
        assert skillopt.main(argv) == 2
