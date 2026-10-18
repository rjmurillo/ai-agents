"""Tests for the skillopt CLI: budget, gate, pair-gate, and score."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import skillopt
from skillopt_helpers import (
    Capture,
    write_json,
)

SHA_ARGS = ["--incumbent-sha256", "a" * 64, "--null-sha256", "a" * 64]


class PairGateFiles:
    """Writes the JSON inputs for a pair-gate invocation."""

    def __init__(
        self, tmp_path: Path, eval_doc: object, incumbent: object, candidate: object
    ) -> None:
        self.ev = write_json(tmp_path / "e.json", eval_doc)
        self.incumbent = write_json(tmp_path / "incumbent.json", incumbent)
        self.candidate = write_json(tmp_path / "candidate.json", candidate)

    def argv(self, *extra: str) -> list[str]:
        return [
            "pair-gate", "--eval", str(self.ev),
            "--incumbent-results", str(self.incumbent),
            "--candidate-results", str(self.candidate),
            *extra,
        ]  # fmt: skip


class TestCli:
    def test_budget_cmd(self, capsys: Capture) -> None:
        assert (
            skillopt.main(["budget", "--step", "0", "--total", "10", "--max", "5", "--min", "1"])
            == 0
        )
        assert capsys.readouterr().out.strip() == "5"

    def test_budget_invalid_exit_two(self, capsys: Capture) -> None:
        assert skillopt.main(["budget", "--step", "10", "--total", "10"]) == 2
        assert "skillopt:" in capsys.readouterr().err

    def test_budget_last_valid_step_is_total_minus_one(self, capsys: Capture) -> None:
        assert skillopt.main(["budget", "--step", "2", "--total", "3"]) == 0
        assert capsys.readouterr().out.strip() == "1"

    def test_budget_step_equal_to_total_names_zero_based_range(self, capsys: Capture) -> None:
        assert skillopt.main(["budget", "--step", "3", "--total", "3"]) == 2
        assert "out of range [0, 3)" in capsys.readouterr().err

    def test_budget_negative_step_exit_two(self, capsys: Capture) -> None:
        assert skillopt.main(["budget", "--step", "-1", "--total", "3"]) == 2
        assert "out of range [0, 3)" in capsys.readouterr().err

    @pytest.mark.parametrize("command", ["budget", "buffer-add"])
    def test_step_help_states_zero_based(self, command: str, capsys: Capture) -> None:
        with pytest.raises(SystemExit) as exc:
            skillopt.main([command, "--help"])
        assert exc.value.code == 0
        out = " ".join(capsys.readouterr().out.split())
        assert "0-based step index" in out

    def test_budget_total_help_states_step_bound(self, capsys: Capture) -> None:
        with pytest.raises(SystemExit):
            skillopt.main(["budget", "--help"])
        out = " ".join(capsys.readouterr().out.split())
        assert "--step must be less than N" in out

    def test_gate_accept_exit_zero(self, capsys: Capture) -> None:
        assert skillopt.main(["gate", "--candidate", "0.9", "--incumbent", "0.8"]) == 0
        assert "ACCEPT" in capsys.readouterr().out

    def test_gate_reject_exit_one(self, capsys: Capture) -> None:
        assert skillopt.main(["gate", "--candidate", "0.8", "--incumbent", "0.8"]) == 1
        assert "REJECT" in capsys.readouterr().out

    def test_pair_gate_accepts_exit_zero(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(
            tmp_path,
            {"splits": {"sel": ["semantic", "context"]}},
            {"semantic": True, "context": False},
            {"semantic": True, "context": True},
        )
        assert skillopt.main(files.argv()) == 0
        assert json.loads(capsys.readouterr().out)["verdict"] == "ACCEPT_PARETO"

    def test_pair_gate_rejects_regression_exit_one(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(
            tmp_path,
            {"splits": {"sel": ["a", "b"]}},
            {"a": True, "b": False},
            {"a": False, "b": True},
        )
        assert skillopt.main(files.argv()) == 1
        assert json.loads(capsys.readouterr().out)["verdict"] == "REJECT"

    def test_pair_gate_unverified_exit_one(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(
            tmp_path, {"splits": {"sel": ["a"]}}, {"a": False}, {"a": "UNVERIFIED"}
        )
        assert skillopt.main(files.argv()) == 1
        assert json.loads(capsys.readouterr().out)["verdict"] == "REJECT_UNVERIFIED"

    def test_pair_gate_null_results_flag(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(tmp_path, {"splits": {"sel": ["a"]}}, {"a": False}, {"a": True})
        null = write_json(tmp_path / "null.json", {"a": True})
        assert skillopt.main(files.argv("--null-results", str(null), *SHA_ARGS)) == 1
        assert json.loads(capsys.readouterr().out)["verdict"] == "REJECT_NULL_CONTROL"

    def test_pair_gate_null_results_accept(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(tmp_path, {"splits": {"sel": ["a"]}}, {"a": False}, {"a": True})
        null = write_json(tmp_path / "null.json", {"a": False})
        assert skillopt.main(files.argv("--null-results", str(null), *SHA_ARGS)) == 0
        assert json.loads(capsys.readouterr().out)["genuine_gains"] == ["a"]

    def test_pair_gate_null_results_without_hashes_exit_two(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        files = PairGateFiles(tmp_path, {"splits": {"sel": ["a"]}}, {"a": False}, {"a": True})
        null = write_json(tmp_path / "null.json", {"a": False})
        assert skillopt.main(files.argv("--null-results", str(null))) == 2
        assert "--incumbent-sha256" in capsys.readouterr().err

    def test_pair_gate_null_hash_mismatch_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(tmp_path, {"splits": {"sel": ["a"]}}, {"a": False}, {"a": True})
        null = write_json(tmp_path / "null.json", {"a": False})
        argv = files.argv("--null-results", str(null))
        argv += ["--incumbent-sha256", "a" * 64, "--null-sha256", "b" * 64]
        assert skillopt.main(argv) == 2
        assert "byte-identical incumbent" in capsys.readouterr().err

    def test_pair_gate_nondeterministic_scorer_needs_null_exit_two(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        eval_doc = {"splits": {"sel": ["a"]}, "scorer": "nondeterministic"}
        files = PairGateFiles(tmp_path, eval_doc, {"a": False}, {"a": True})
        assert skillopt.main(files.argv()) == 2
        assert "nondeterministic scorer requires --null-results" in capsys.readouterr().err

    def test_pair_gate_nondeterministic_scorer_with_null_runs(self, tmp_path: Path) -> None:
        eval_doc = {"splits": {"sel": ["a"]}, "scorer": "nondeterministic"}
        files = PairGateFiles(tmp_path, eval_doc, {"a": False}, {"a": True})
        null = write_json(tmp_path / "null.json", {"a": False})
        assert skillopt.main(files.argv("--null-results", str(null), *SHA_ARGS)) == 0

    def test_pair_gate_unknown_scorer_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        eval_doc = {"splits": {"sel": ["a"]}, "scorer": "flaky"}
        files = PairGateFiles(tmp_path, eval_doc, {"a": False}, {"a": True})
        assert skillopt.main(files.argv()) == 2
        assert "'scorer' must be one of" in capsys.readouterr().err

    def test_pair_gate_train_review_with_exposed_tasks_works(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        eval_doc = {"splits": {"sel": ["s"], "train": ["a"]}, "exposed": ["a"]}
        files = PairGateFiles(tmp_path, eval_doc, {"a": False}, {"a": True})
        assert skillopt.main(files.argv("--split", "train")) == 0
        assert json.loads(capsys.readouterr().out)["split"] == "train"

    def test_pair_gate_exposed_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(
            tmp_path, {"splits": {"sel": ["a"]}, "exposed": ["a"]}, {"a": False}, {"a": True}
        )
        assert skillopt.main(files.argv()) == 2
        assert "exposed or invalid: a" in capsys.readouterr().err

    def test_pair_gate_empty_split_exit_two(self, tmp_path: Path) -> None:
        files = PairGateFiles(tmp_path, {"splits": {"sel": []}}, {}, {})
        assert skillopt.main(files.argv()) == 2

    def test_pair_gate_missing_split_exit_two(self, tmp_path: Path) -> None:
        files = PairGateFiles(tmp_path, {"splits": {}}, {}, {})
        assert skillopt.main(files.argv()) == 2

    @pytest.mark.parametrize(
        ("eval_doc", "incumbent_doc", "candidate_doc", "null_doc", "message"),
        [
            ([], {}, {}, {}, "pair-gate eval input must be a JSON object"),
            ({}, [], {}, {}, "pair-gate incumbent results must be a JSON object"),
            ({}, {}, [], {}, "pair-gate candidate results must be a JSON object"),
            ({}, {}, {}, [], "pair-gate null results must be a JSON object"),
        ],
    )
    def test_pair_gate_rejects_non_object_inputs(
        self,
        tmp_path: Path,
        capsys: Capture,
        eval_doc: object,
        incumbent_doc: object,
        candidate_doc: object,
        null_doc: object,
        message: str,
    ) -> None:
        files = PairGateFiles(tmp_path, eval_doc, incumbent_doc, candidate_doc)
        null = write_json(tmp_path / "null.json", null_doc)
        assert skillopt.main(files.argv("--null-results", str(null))) == 2
        assert message in capsys.readouterr().err

    def test_pair_gate_invalid_json_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(tmp_path, {"splits": {"sel": ["a"]}}, {}, {})
        files.candidate.write_text("{nope", encoding="utf-8")
        assert skillopt.main(files.argv()) == 2
        assert capsys.readouterr().err.startswith("skillopt: ")

    def test_pair_gate_missing_file_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        files = PairGateFiles(tmp_path, {"splits": {"sel": ["a"]}}, {}, {})
        files.incumbent.unlink()
        assert skillopt.main(files.argv()) == 2
        assert "incumbent.json" in capsys.readouterr().err

    def test_non_utf8_input_exit_two(self, tmp_path: Path, capsys: Capture) -> None:
        bad = tmp_path / "bad.json"
        bad.write_bytes(b"\xff\xfe")
        assert skillopt.main(["score", "--eval", str(bad), "--results", str(bad)]) == 2
        assert capsys.readouterr().err.startswith("skillopt: ")

    def test_score_cmd(self, tmp_path: Path, capsys: Capture) -> None:
        ev = write_json(tmp_path / "e.json", {"splits": {"sel": ["t1", "t2"]}})
        res = write_json(tmp_path / "r.json", {"t1": True, "t2": False})
        assert skillopt.main(["score", "--eval", str(ev), "--results", str(res)]) == 0
        assert capsys.readouterr().out.strip() == "0.500000"

    @pytest.mark.parametrize(
        ("eval_doc", "results_doc", "message"),
        [
            ([], {}, "score eval input must be a JSON object"),
            ({}, [], "score results must be a JSON object"),
        ],
    )
    def test_score_non_object_exit_two(
        self, tmp_path: Path, capsys: Capture, eval_doc: object, results_doc: object, message: str
    ) -> None:
        ev = write_json(tmp_path / "e.json", eval_doc)
        res = write_json(tmp_path / "r.json", results_doc)
        assert skillopt.main(["score", "--eval", str(ev), "--results", str(res)]) == 2
        assert message in capsys.readouterr().err

    def test_missing_subcommand_errors(self) -> None:
        with pytest.raises(SystemExit):
            skillopt.build_parser().parse_args([])
