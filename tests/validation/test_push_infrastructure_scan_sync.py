"""Pre-push security gate: syncing with main and editing comments (issue #6509).

A reviewed branch that merges main used to fail the gate, because the pushed tip
became a merge commit. A one-line comment edit in a workflow used to demand a
full security review. These cases run the real hook, detector, and git history
end to end. Shared scaffolding lives in ``_push_scan_repo.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation._push_scan_repo import (
    WORKFLOW,
    Origin,
    commit,
    git,
    marker,
    new_branch_line,
    pre_push,
    work_clone,
)

WORKFLOW_TEXT = "# build the project\non: push\n"


@pytest.fixture
def origin(tmp_path: Path) -> Origin:
    return Origin(tmp_path)


def _reviewed_workflow_branch(origin: Origin, tmp_path: Path) -> Path:
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/ci")
    commit(work, WORKFLOW, "on: push\n")
    marker(work)
    return work


def test_reviewed_branch_that_merged_main_passes(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work = _reviewed_workflow_branch(origin, tmp_path)
    origin.advance_main("docs/main.md")
    git(work, "fetch", "-q", "origin")
    git(work, "merge", "-q", "--no-edit", "origin/main")
    head = git(work, "rev-parse", "HEAD")

    result = pre_push(work, new_branch_line("feature/ci", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "scores 1 file(s)" in err


def test_merge_with_an_extra_edit_is_still_blocked(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work = _reviewed_workflow_branch(origin, tmp_path)
    origin.advance_main("docs/main.md")
    git(work, "fetch", "-q", "origin")
    git(work, "merge", "-q", "--no-commit", "--no-ff", "origin/main")
    (work / WORKFLOW).write_text("on: pull_request_target\n", encoding="utf-8")
    git(work, "add", WORKFLOW)
    git(work, "commit", "-q", "-m", "merge main")
    head = git(work, "rev-parse", "HEAD")

    result = pre_push(work, new_branch_line("feature/ci", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "beyond a clean merge" in err


def _workflow_on_main_clone(origin: Origin, tmp_path: Path) -> Path:
    git(origin.seed, "pull", "-q", "--ff-only", "origin", "main")
    commit(origin.seed, WORKFLOW, WORKFLOW_TEXT)
    git(origin.seed, "push", "-q", "origin", "HEAD:main")
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/ci-note")
    return work


def test_comment_only_workflow_edit_passes_without_a_marker(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work = _workflow_on_main_clone(origin, tmp_path)
    head = commit(work, WORKFLOW, WORKFLOW_TEXT.replace("build the project", "compile it"))

    result = pre_push(work, new_branch_line("feature/ci-note", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "comments only" in err


def test_code_edit_to_the_same_workflow_is_blocked_without_a_marker(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    work = _workflow_on_main_clone(origin, tmp_path)
    head = commit(work, WORKFLOW, WORKFLOW_TEXT.replace("push", "pull_request_target"))

    result = pre_push(work, new_branch_line("feature/ci-note", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "CRITICAL change without a security review marker" in err
