"""Tests for the saved change patch in the ablation CLI (issue #5768).

The patch is the agent's change, taken before the hidden follow-up files are
written, and it is saved for every run so a human has something to correct and
time. The Claude CLI is never invoked for real: `FakeClaudeRunner` plays its part.
Git and `python3` grading run for real.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._control_ablation_test_support import (
    FakeClaudeRunner,
    cli,
    grade,
    live_reduced_args,
    load_tasks,
)

TASK = "hidden-regression"
REVIEWER_MODEL = "claude-sonnet-5"
PATCH = "changes/reduced/hidden-regression-r0.patch"
HIDDEN_PATH = "followup/test_hidden.py"


def _report(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))


def _patch(tmp_path: Path) -> str:
    return (tmp_path / "out" / PATCH).read_text(encoding="utf-8")


def test_a_reverted_change_keeps_its_patch_file_and_the_workspace_is_reverted(
    tmp_path: Path,
) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_bad")

    cli.main(live_reduced_args(tmp_path, "--only-tasks", TASK), runner=runner)

    (run,) = _report(tmp_path)["runs"]
    assert run["change_patch"] == PATCH
    assert "calc/core.py" in _patch(tmp_path) and "+    return 3" in _patch(tmp_path)
    workspace = tmp_path / "ws" / f"{TASK}-reduced-0"
    assert grade.changed_paths(workspace) == ()


def test_a_change_that_needed_no_revert_also_keeps_its_patch(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_good")

    cli.main(live_reduced_args(tmp_path, "--only-tasks", TASK), runner=runner)

    assert "+    return a - b" in _patch(tmp_path)


def test_the_patch_holds_no_hidden_follow_up_path(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_bad")

    cli.main(live_reduced_args(tmp_path, "--only-tasks", TASK), runner=runner)

    patch = _patch(tmp_path)
    assert "followup/" not in patch and "test_hidden" not in patch
    assert "calc/core.py" in patch


def test_an_agent_edit_at_a_follow_up_path_stays_in_the_patch_with_the_agent_bytes(
    tmp_path: Path,
) -> None:
    mine = "# the agent wrote this file\n"
    runner = FakeClaudeRunner(
        load_tasks(tmp_path), kind="known_good", extra_files={HIDDEN_PATH: mine}
    )

    cli.main(live_reduced_args(tmp_path, "--only-tasks", TASK), runner=runner)

    patch = _patch(tmp_path)
    assert f"+++ b/{HIDDEN_PATH}" in patch and "+# the agent wrote this file" in patch
    assert "TestSubtract" not in patch


def test_the_reviewer_copy_never_holds_the_hidden_follow_up_content(tmp_path: Path) -> None:
    mine = "# the agent wrote this file\n"
    runner = FakeClaudeRunner(
        load_tasks(tmp_path), kind="known_good", extra_files={HIDDEN_PATH: mine}
    )
    args = live_reduced_args(tmp_path, "--only-tasks", TASK, "--reviewer-model", REVIEWER_MODEL)

    code = cli.main(args, runner=runner)

    # The hidden test fails on the agent's stand-in file, so acceptance may or may not pass;
    # when a reviewer ran, its copy must hold the agent's bytes, never the hidden test.
    assert code == cli.EXIT_OK
    for seen in runner.review_calls:
        contents = seen["contents"]
        assert "TestSubtract" not in "".join(contents.values())
        assert contents.get(HIDDEN_PATH, mine) == mine


def test_the_reviewer_copy_of_an_untouched_follow_up_path_is_absent(tmp_path: Path) -> None:
    runner = FakeClaudeRunner(load_tasks(tmp_path), kind="known_good")
    args = live_reduced_args(tmp_path, "--only-tasks", TASK, "--reviewer-model", REVIEWER_MODEL)

    cli.main(args, runner=runner)

    (seen,) = runner.review_calls
    assert not [f for f in seen["files"] if f.startswith("followup/")]


def test_a_run_that_changed_nothing_writes_an_empty_patch(tmp_path: Path) -> None:
    tasks = load_tasks(tmp_path)
    emptied = [
        dataclasses.replace(
            task,
            controls={
                kind: dataclasses.replace(control, files={})
                for kind, control in task.controls.items()
            },
        )
        for task in tasks
    ]
    runner = FakeClaudeRunner(emptied, kind="known_good")

    cli.main(live_reduced_args(tmp_path, "--only-tasks", TASK), runner=runner)

    assert _patch(tmp_path) == ""


def test_snapshot_diff_includes_untracked_files(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    task = load_tasks(tmp_path)[0]
    grade.seed_workspace(workspace, task, {})
    (workspace / "brand_new.py").write_text("x = 1\n", encoding="utf-8")

    patch = grade.snapshot_diff(workspace)

    assert "brand_new.py" in patch and "+x = 1" in patch


def test_snapshot_diff_is_empty_outside_a_repository(tmp_path: Path) -> None:
    assert grade.snapshot_diff(tmp_path) == ""


def test_the_human_minutes_flag_is_gone_from_the_ablation_cli(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(live_reduced_args(tmp_path, "--human-minutes", str(tmp_path / "m.json")))
    assert exc.value.code == 2
