"""Tests for per-repeat variance reporting (issue #5768)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import _durable_repetitions as reps
import eval_durable_repetitions as cli
import pytest
from _outcome_record import parse_record

from tests.eval._durable_outcome_test_support import EVAL_DIR, make_config, make_record

SCRIPT = EVAL_DIR / "eval_durable_repetitions.py"


def _rec(task: str, repeat: int, *, cost: float = 0.5, **overrides: Any) -> Any:
    data = make_record(task_id=task, repeat=repeat, **overrides)
    data["economics"] = {**data["economics"], "model_cost_usd": cost}
    return parse_record(data)


def _rejected(task: str, repeat: int, cost: float = 0.5) -> Any:
    data = make_record(task_id=task, repeat=repeat)
    data["execution"] = {**data["execution"], "deterministic_acceptance": "FAIL"}
    data["economics"] = {**data["economics"], "model_cost_usd": cost}
    return parse_record(data)


def _not_durable(task: str, repeat: int, cost: float = 0.5) -> Any:
    data = make_record(task_id=task, repeat=repeat)
    data["durable"] = {**data["durable"], "followup_validation": "FAIL"}
    data["economics"] = {**data["economics"], "model_cost_usd": cost}
    return parse_record(data)


class TestRepetitionSummary:
    def test_counts_each_verdict_per_repeat(self) -> None:
        records = [
            _rec("a", 0),
            _rejected("b", 0),
            _not_durable("a", 1),
            _rec("b", 1),
        ]

        summary = reps.repetition_summary(records)
        first, second = summary["per_repeat"]  # type: ignore[misc]

        assert (first["accepted_durable"], first["rejected"]) == (1, 1)
        assert (second["accepted_durable"], second["accepted_not_durable"]) == (1, 1)

    def test_cost_per_durable_keeps_rejected_cost_in_the_numerator(self) -> None:
        records = [_rec("a", 0, cost=0.25), _rejected("b", 0, cost=0.75)]

        row = reps.repetition_summary(records)["per_repeat"][0]  # type: ignore[index]

        assert row["cost_per_durable_usd"] == 1.0

    def test_spread_reports_mean_sample_stdev_min_and_max(self) -> None:
        records = [
            _rec("a", 0),
            _rec("b", 0),
            _rec("a", 1),
            _rejected("b", 1),
            _rejected("a", 2),
            _rejected("b", 2),
        ]

        spread = reps.repetition_summary(records)["accepted_durable_spread"]

        assert spread == {"n": 3, "mean": 1.0, "stdev": 1.0, "min": 0.0, "max": 2.0}

    def test_a_repeat_without_a_durable_accept_has_no_cost_and_is_counted(self) -> None:
        records = [_rec("a", 0, cost=0.4), _rejected("a", 1)]

        summary = reps.repetition_summary(records)

        assert summary["repeats_without_durable"] == 1
        assert summary["cost_per_durable_spread_usd"]["n"] == 1  # type: ignore[index]
        assert summary["cost_per_durable_spread_usd"]["stdev"] is None  # type: ignore[index]

    def test_no_durable_accept_anywhere_leaves_empty_cost_statistics(self) -> None:
        summary = reps.repetition_summary([_rejected("a", 0)])

        assert summary["cost_per_durable_spread_usd"]["mean"] is None  # type: ignore[index]

    def test_a_task_with_mixed_verdicts_is_named(self) -> None:
        records = [_rec("a", 0), _rejected("a", 1), _rec("b", 0), _rec("b", 1)]

        summary = reps.repetition_summary(records)

        assert summary["tasks_with_mixed_verdicts"] == ["a"]
        rows = {row["task_id"]: row for row in summary["per_task"]}  # type: ignore[attr-defined]
        assert rows["a"]["verdicts"] == ["ACCEPTED_DURABLE", "REJECTED"]
        assert rows["b"]["durable_accepts"] == 2

    def test_no_records_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one record"):
            reps.repetition_summary([])


def _write(path: Path, records: list[dict[str, Any]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return path


class TestCli:
    def test_reads_one_file_and_prints_the_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        file = _write(tmp_path / "a.jsonl", [make_record(repeat=0), make_record(repeat=1)])

        code = cli.main(["--records", str(file)])

        assert code == cli.EXIT_OK
        assert json.loads(capsys.readouterr().out)["repeats"] == 2

    def test_concatenates_chunked_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        one = _write(tmp_path / "one.jsonl", [make_record(repeat=0)])
        two = _write(tmp_path / "two.jsonl", [make_record(repeat=1)])

        code = cli.main(["--records", str(one), "--records", str(two)])

        assert code == cli.EXIT_OK
        assert json.loads(capsys.readouterr().out)["repeats"] == 2

    def test_a_repeated_task_repeat_pair_is_refused(self, tmp_path: Path) -> None:
        file = _write(tmp_path / "a.jsonl", [make_record(repeat=0), make_record(repeat=0)])

        assert cli.main(["--records", str(file)]) == cli.EXIT_INPUT

    def test_mixed_configurations_are_refused(self, tmp_path: Path) -> None:
        other = make_record(repeat=1, config=make_config(control="other"))
        file = _write(tmp_path / "a.jsonl", [make_record(repeat=0), other])

        assert cli.main(["--records", str(file)]) == cli.EXIT_INPUT

    def test_a_missing_file_is_refused(self, tmp_path: Path) -> None:
        assert cli.main(["--records", str(tmp_path / "absent.jsonl")]) == cli.EXIT_INPUT

    def test_malformed_json_is_refused(self, tmp_path: Path) -> None:
        file = tmp_path / "bad.jsonl"
        file.write_text("{not json\n", encoding="utf-8")

        assert cli.main(["--records", str(file)]) == cli.EXIT_INPUT

    def test_an_empty_file_is_refused(self, tmp_path: Path) -> None:
        file = tmp_path / "empty.jsonl"
        file.write_text("", encoding="utf-8")

        assert cli.main(["--records", str(file)]) == cli.EXIT_INPUT

    def test_the_script_runs_as_a_process(self, tmp_path: Path) -> None:
        file = _write(tmp_path / "a.jsonl", [make_record()])

        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--records", str(file)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        assert done.returncode == 0 and json.loads(done.stdout)["repeats"] == 1
