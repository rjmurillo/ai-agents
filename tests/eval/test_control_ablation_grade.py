"""Tests for scripts/eval/_control_ablation_grade.py (REQ-043 AC-4, AC-5).

Real temporary git repositories and real `python3` commands, per
TASK-052 milestone 3. No mocks for git or the interpreter; the only
double in this file is the task fixture data itself.
"""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import pytest

from tests.eval._control_ablation_test_support import (
    ablation_tasks,
    grade,
    make_task_document,
)


def _hidden_regression_task() -> ablation_tasks.Task:
    tasks = ablation_tasks.load_tasks(make_task_document())
    return next(t for t in tasks if t.id == "hidden-regression")


def _seeded(tmp_path: Path) -> tuple[Path, ablation_tasks.Task]:
    workspace = tmp_path / "workspace"
    task = _hidden_regression_task()
    grade.seed_workspace(workspace, task, {})
    return workspace, task


def test_seed_workspace_creates_a_git_repo_with_setup_files_committed(tmp_path: Path) -> None:
    workspace, _task = _seeded(tmp_path)
    assert (workspace / ".git").is_dir()
    assert (workspace / "calc" / "core.py").is_file()
    assert (workspace / "tests" / "test_core.py").is_file()
    # No follow-up file before the agent runs (REQ-043 data-model invariant).
    assert not (workspace / "followup" / "test_hidden.py").exists()


def test_seed_workspace_installs_control_files_alongside_setup_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    task = _hidden_regression_task()
    grade.seed_workspace(workspace, task, {"AGENTS.md": "control content\n"})
    assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "control content\n"


def test_changed_paths_is_empty_immediately_after_seed(tmp_path: Path) -> None:
    workspace, _task = _seeded(tmp_path)
    assert grade.changed_paths(workspace) == ()


def test_changed_paths_reports_a_modified_and_a_new_file(tmp_path: Path) -> None:
    workspace, task = _seeded(tmp_path)
    good = task.controls["known_good"]
    grade.apply_control_files(workspace, good.files)
    (workspace / "notes.txt").write_text("scratch\n", encoding="utf-8")
    changed = grade.changed_paths(workspace)
    assert "calc/core.py" in changed
    assert "notes.txt" in changed


def test_added_lines_by_python_path_returns_only_plus_lines(tmp_path: Path) -> None:
    workspace, task = _seeded(tmp_path)
    grade.apply_control_files(workspace, task.controls["known_good"].files)
    changed = grade.changed_paths(workspace)
    added = grade.added_lines_by_python_path(workspace, changed)
    assert "calc/core.py" in added
    assert "def subtract" in added["calc/core.py"]
    assert "def add" not in added["calc/core.py"]  # unchanged line, not a '+' line


def test_added_lines_by_python_path_skips_non_python_files(tmp_path: Path) -> None:
    workspace, _task = _seeded(tmp_path)
    (workspace / "notes.txt").write_text("scratch\n", encoding="utf-8")
    changed = grade.changed_paths(workspace)
    added = grade.added_lines_by_python_path(workspace, changed)
    assert "notes.txt" not in added


def test_run_acceptance_passes_on_the_seeded_workspace(tmp_path: Path) -> None:
    workspace, task = _seeded(tmp_path)
    result = grade.run_acceptance(workspace, task)
    assert result.returncode == 0


def test_run_acceptance_passes_for_known_good_and_known_bad_alike(tmp_path: Path) -> None:
    # The hidden-regression case's visible test suite does not exercise
    # subtract(); both controls pass acceptance, and only the follow-up
    # suite (run separately below) discriminates them.
    for control_name in ("known_good", "known_bad"):
        workspace = tmp_path / control_name
        task = _hidden_regression_task()
        grade.seed_workspace(workspace, task, {})
        grade.apply_control_files(workspace, task.controls[control_name].files)
        result = grade.run_acceptance(workspace, task)
        assert result.returncode == 0, f"{control_name}: {result.stdout}\n{result.stderr}"


def test_run_followup_discriminates_known_good_from_known_bad(tmp_path: Path) -> None:
    outcomes: dict[str, int] = {}
    for control_name in ("known_good", "known_bad"):
        workspace = tmp_path / control_name
        task = _hidden_regression_task()
        grade.seed_workspace(workspace, task, {})
        grade.apply_control_files(workspace, task.controls[control_name].files)
        grade.write_followup_files(workspace, task)
        result = grade.run_followup(workspace, task)
        outcomes[control_name] = result.returncode
    assert outcomes["known_good"] == 0
    assert outcomes["known_bad"] != 0


def test_write_followup_files_writes_after_the_fact(tmp_path: Path) -> None:
    workspace, task = _seeded(tmp_path)
    assert not (workspace / "followup" / "test_hidden.py").exists()
    grade.write_followup_files(workspace, task)
    assert (workspace / "followup" / "test_hidden.py").is_file()


def test_external_marker_exists_false_when_task_has_none(tmp_path: Path) -> None:
    workspace, task = _seeded(tmp_path)
    assert grade.external_marker_exists(workspace, task) is False


def test_external_marker_exists_true_when_the_file_is_present(tmp_path: Path) -> None:
    tasks = ablation_tasks.load_tasks(make_task_document())
    task = next(t for t in tasks if t.id == "consequential-hold")
    task = dataclasses.replace(task, external_marker="PUBLISHED")
    workspace = tmp_path / "workspace"
    grade.seed_workspace(workspace, task, {})
    assert grade.external_marker_exists(workspace, task) is False
    (workspace / "PUBLISHED").write_text("done\n", encoding="utf-8")
    assert grade.external_marker_exists(workspace, task) is True


def test_safe_file_refuses_a_path_escaping_the_workspace(tmp_path: Path) -> None:
    workspace, task = _seeded(tmp_path)
    task = dataclasses.replace(task, external_marker="../../etc/passwd")
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="escapes"):
        grade.external_marker_exists(workspace, task)


def test_run_acceptance_times_out_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, task = _seeded(tmp_path)
    monkeypatch.setattr(grade, "GRADE_TIMEOUT", 0.01)
    slow_task = dataclasses.replace(
        task, acceptance=("python3", "-c", "import time; time.sleep(5)")
    )
    result = grade.run_acceptance(workspace, slow_task)
    assert result.returncode != 0


def test_changed_paths_include_work_the_agent_committed(tmp_path: Path) -> None:
    task = next(
        t for t in ablation_tasks.load_tasks(make_task_document()) if t.id == "hidden-regression"
    )
    workspace = tmp_path / "ws"
    grade.seed_workspace(workspace, task, {})
    edited = "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n"
    (workspace / "calc" / "core.py").write_text(edited, encoding="utf-8")
    commit = ["-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "x"]
    for args in (["add", "-A"], commit):
        subprocess.run(["git", *args], cwd=workspace, check=True, capture_output=True)

    changed = grade.changed_paths(workspace)

    assert changed == ("calc/core.py",)


def test_agent_git_add_cannot_stage_the_harness_profile(tmp_path: Path) -> None:
    task = next(
        t for t in ablation_tasks.load_tasks(make_task_document()) if t.id == "hidden-regression"
    )
    workspace = tmp_path / "ws"
    grade.seed_workspace(workspace, task, {})
    secret = workspace / ".parity-profile" / "claude" / ".credentials.json"
    secret.parent.mkdir(parents=True)
    secret.write_text("secret", encoding="utf-8")

    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, capture_output=True)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout

    assert ".parity-profile" not in staged
