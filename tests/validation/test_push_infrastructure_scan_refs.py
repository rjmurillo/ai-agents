"""Ref-shape and failure-path cases for the pre-push infrastructure scan (issue #6076).

Tags, notes, multi-ref pushes, renames, fetch and diff failures, and the
short-circuit after a branch policy failure. Core acceptance cases live in
``test_push_infrastructure_scan.py``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy
from tests.validation._push_scan_repo import (
    WORKFLOW,
    ZERO,
    Origin,
    commit,
    git,
    new_branch_line,
    pre_push,
    work_clone,
)


@pytest.fixture
def origin(tmp_path: Path) -> Origin:
    return Origin(tmp_path)


def test_push_with_no_changed_files_skips_the_detector_and_reports_zero(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A branch at origin/main scores zero files, reported, without the detector."""
    work = work_clone(origin, tmp_path, detector=False)
    git(work, "checkout", "-q", "-b", "feature/empty", "origin/main")
    head = git(work, "rev-parse", "HEAD")

    result = pre_push(work, new_branch_line("feature/empty", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/empty scores 0 file(s)" in err


def test_failed_diff_fails_loud(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC5: a diff git cannot produce is a config error, not an empty file list."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")
    real_run_git = policy._run_git

    def failing_scan_diff(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["diff", "--name-only", "-z", "--no-renames"]:
            return subprocess.CompletedProcess(args, 128, "", "fatal: bad object\n")
        return real_run_git(repo_root, args)

    monkeypatch.setattr(policy, "_run_git", failing_scan_diff)

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "could not diff" in err
    assert "scores" not in err


def test_branch_policy_failure_returns_before_the_scan(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scan runs only after the per-update branch policies pass."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")
    scanned: list[object] = []

    def record_scan(*args: object) -> int:
        scanned.append(args)
        return 0

    monkeypatch.setattr(policy, "_check_push_updates", lambda *_args: 1)
    monkeypatch.setattr(policy, "check_pushed_infrastructure", record_scan)

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    assert result == 1
    assert scanned == []


def test_tag_push_with_workflow_change_and_no_marker_is_blocked(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A tag runs its commit's workflows, so a tag push is scored like a branch."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/release")
    head = commit(work, WORKFLOW, "on: push\n")
    git(work, "tag", "v9.9.9", head)
    line = f"refs/tags/v9.9.9 {head} refs/tags/v9.9.9 {ZERO}\n"

    result = pre_push(work, line, monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "refs/tags/v9.9.9 scores 1 file(s)" in err


def test_tag_on_main_scores_nothing_and_notes_refs_are_skipped(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A release tag on main carries no branch change; a notes ref is not scanned."""
    work = work_clone(origin, tmp_path, detector=False)
    git(work, "checkout", "-q", "-b", "feature/other", "origin/main")
    main_tip = git(work, "rev-parse", "origin/main")
    git(work, "notes", "add", "-m", "note", main_tip)
    notes = git(work, "rev-parse", "refs/notes/commits")

    tag = pre_push(work, f"refs/tags/v1 {main_tip} refs/tags/v1 {ZERO}\n", monkeypatch)
    tag_err = capsys.readouterr().err
    note = pre_push(work, f"refs/notes/commits {notes} refs/notes/commits {ZERO}\n", monkeypatch)
    note_err = capsys.readouterr().err

    assert tag == 0, tag_err
    assert "refs/tags/v1 scores 0 file(s)" in tag_err
    assert note == 0, note_err
    assert "skipped, no branch or tag ref in this push carries commits" in note_err


def test_multi_ref_push_blocks_when_only_the_second_ref_is_unreviewed(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every ref is scored; one clean ref does not cover another."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    docs = commit(work, "docs/note.md", "note\n")
    git(work, "checkout", "-q", "-b", "feature/ci", "origin/main")
    ci = commit(work, WORKFLOW, "on: push\n")
    payload = new_branch_line("feature/docs", docs) + new_branch_line("feature/ci", ci)

    result = pre_push(work, payload, monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "refs/heads/feature/docs scores 1 file(s)" in err
    assert "refs/heads/feature/ci scores 1 file(s)" in err


def test_renaming_a_workflow_away_still_scores_the_workflow_path(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--no-renames reports both sides, so moving a workflow out is still CRITICAL."""
    origin.advance_main(WORKFLOW)
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/move")
    git(work, "mv", WORKFLOW, "ci-moved.yml")
    git(work, "commit", "-qm", "test: move workflow")
    head = git(work, "rev-parse", "HEAD")

    result = pre_push(work, new_branch_line("feature/move", head), monkeypatch)

    captured = capsys.readouterr()
    assert result == 1, captured.err
    assert "scores 2 file(s)" in captured.err
    assert WORKFLOW in captured.out


def test_failed_fetch_warns_and_still_scores_from_local_origin_main(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC8: an unreachable origin warns; the local origin/main still gives a base."""
    work = work_clone(origin, tmp_path)
    git(work, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "could not refresh origin/main" in err
    assert "refs/heads/feature/docs scores 1 file(s)" in err
