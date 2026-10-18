"""Tests for `--human-minutes` and the rolled-back patch in the ablation CLI (issue #5768).

The Claude CLI is never invoked for real: `FakeClaudeRunner` plays its part. Git and
`python3` grading run for real.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_test_support import (
    FakeClaudeRunner,
    cli,
    durable_outcome,
    grade,
    live_reduced_args,
    load_tasks,
    outcome,
)

TASK = "hidden-regression"
REVIEWER_MODEL = "claude-sonnet-5"


def _minutes(tmp_path: Path, rows: list[dict[str, Any]] | str) -> str:
    path = tmp_path / "minutes.json"
    path.write_text(rows if isinstance(rows, str) else json.dumps(rows), encoding="utf-8")
    return str(path)


def _row(minutes: float = 2.0, control: str = "reduced", task: str = TASK) -> dict[str, Any]:
    return {"control": control, "task_id": task, "repeat": 0, "minutes": minutes}


def _record(tmp_path: Path) -> outcome.OutcomeRecord:
    path = tmp_path / "out" / "records-reduced.jsonl"
    (line,) = path.read_text(encoding="utf-8").splitlines()
    return outcome.parse_record(json.loads(line))


def _report(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))


def test_a_timed_row_lets_a_reviewed_accepted_change_verify(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_good")
    args = live_reduced_args(
        tmp_path,
        "--only-tasks",
        TASK,
        "--reviewer-model",
        REVIEWER_MODEL,
        "--human-minutes",
        _minutes(tmp_path, [_row(minutes=0)]),
    )

    code = cli.main(args, runner=runner)

    assert code == cli.EXIT_OK
    record = _record(tmp_path)
    assert record.economics.human_correction_minutes == 0.0
    assert durable_outcome.classify(record) is durable_outcome.Verdict.ACCEPTED_DURABLE
    report = _report(tmp_path)
    assert report["human_minutes_rows"] == 1 and report["human_minutes_unmatched"] == []


def test_a_timed_row_without_a_reviewer_still_leaves_review_findings_null(
    tmp_path: Path,
) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_good")
    args = live_reduced_args(
        tmp_path, "--only-tasks", TASK, "--human-minutes", _minutes(tmp_path, [_row(minutes=3.5)])
    )

    cli.main(args, runner=runner)

    record = _record(tmp_path)
    assert record.economics.human_correction_minutes == 3.5
    assert record.durable.review_findings is None
    assert durable_outcome.classify(record) is durable_outcome.Verdict.UNVERIFIED


def test_an_unmatched_row_is_reported_and_the_cell_stays_null(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_good")
    args = live_reduced_args(
        tmp_path, "--only-tasks", TASK, "--human-minutes", _minutes(tmp_path, [_row(task="absent")])
    )

    cli.main(args, runner=runner)

    assert _record(tmp_path).economics.human_correction_minutes is None
    assert _report(tmp_path)["human_minutes_unmatched"] == [["reduced", "absent", 0]]


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", json.dumps([_row(control="nonesuch")]), json.dumps([{"control": "full"}])],
)
def test_a_bad_human_minutes_file_exits_2_before_any_launch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))
    args = live_reduced_args(tmp_path, "--human-minutes", _minutes(tmp_path, content))

    assert cli.main(args, runner=runner) == cli.EXIT_CONFIG
    assert capsys.readouterr().err.startswith("Error:")
    assert runner.calls == []


def test_a_missing_human_minutes_file_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path))
    args = live_reduced_args(tmp_path, "--human-minutes", str(tmp_path / "absent.json"))

    assert cli.main(args, runner=runner) == cli.EXIT_CONFIG
    assert "cannot read" in capsys.readouterr().err


def test_a_reverted_change_keeps_its_patch_in_the_run_entry(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_bad")

    cli.main(live_reduced_args(tmp_path, "--only-tasks", TASK), runner=runner)

    (run,) = _report(tmp_path)["runs"]
    patch = run["rolled_back_patch"]
    assert "calc/core.py" in patch and "+" in patch
    workspace = tmp_path / "ws" / f"{TASK}-reduced-0"
    assert grade.changed_paths(workspace) == ()


def test_a_change_that_needed_no_revert_has_an_empty_patch(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_good")

    cli.main(live_reduced_args(tmp_path, "--only-tasks", TASK), runner=runner)

    assert _report(tmp_path)["runs"][0]["rolled_back_patch"] == ""


def test_snapshot_diff_includes_untracked_files(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    task = load_tasks(tmp_path)[0]
    grade.seed_workspace(workspace, task, {})
    (workspace / "brand_new.py").write_text("x = 1\n", encoding="utf-8")

    patch = grade.snapshot_diff(workspace)

    assert "brand_new.py" in patch and "+x = 1" in patch


def test_snapshot_diff_is_empty_outside_a_repository(tmp_path: Path) -> None:
    assert grade.snapshot_diff(tmp_path) == ""
