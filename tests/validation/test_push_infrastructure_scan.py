"""Pre-push security marker gate scores merge-base(origin/main, pushed SHA) (issue #6076).

Lefthook ``{push_files}`` diffed a new branch against the local ``main`` ref.
When local ``main`` was stale, main's own infrastructure changes counted as the
branch's and ``detect_infrastructure.py --require-security-review`` blocked the
push for files the branch never touched. ``check_push_refs`` now runs the gate
per pushed ref from immutable SHAs. Edge cases live in
``test_push_infrastructure_scan_refs.py``; shared scaffolding in ``_push_scan_repo.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.validation._push_scan_repo import (
    DETECTOR,
    WORKFLOW,
    ZERO,
    Origin,
    commit,
    configure,
    git,
    install_scripts,
    marker,
    new_branch_line,
    pre_push,
    work_clone,
)


@pytest.fixture
def origin(tmp_path: Path) -> Origin:
    return Origin(tmp_path)


def test_stale_local_main_scores_only_the_branch_files(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC1: main's own workflow change must not count as the branch's."""
    work = work_clone(origin, tmp_path)
    stale_main = git(work, "rev-parse", "main")
    origin.advance_main(WORKFLOW)
    git(work, "fetch", "-q", "origin")
    git(work, "checkout", "-q", "-b", "feature/docs", "origin/main")
    head = commit(work, "docs/note.md", "note\n")
    assert git(work, "rev-parse", "main") == stale_main

    # Negative control: the old input, a two-dot diff against local `main`,
    # carries the workflow the branch never touched, and the detector blocks it.
    old_files = git(work, "diff", "--name-only", "main", head).splitlines()
    assert WORKFLOW in old_files
    old = subprocess.run(  # subprocess-encoding: strict-ok
        [
            sys.executable,
            str(work / DETECTOR),
            "--require-security-review",
            "--repo-root",
            str(work),
            "--files",
            *old_files,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert old.returncode == 1, old.stdout + old.stderr

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/docs scores 1 file(s)" in err


def test_fresh_branch_with_workflow_change_and_no_marker_is_blocked(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC2 and AC6: the branch's own CRITICAL file still requires a marker."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/ci")
    head = commit(work, WORKFLOW, "on: push\n")

    result = pre_push(work, new_branch_line("feature/ci", head), monkeypatch)

    captured = capsys.readouterr()
    assert result == 1, captured.err
    assert "scores 1 file(s)" in captured.err
    assert "CRITICAL change without a security review marker" in captured.err
    assert WORKFLOW in captured.out


def test_marker_is_read_from_the_pushed_sha_not_checked_out_head(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC7: a reviewed branch pushed from another checkout passes on its own marker."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/ci")
    commit(work, WORKFLOW, "on: push\n")
    reviewed = marker(work)
    git(work, "checkout", "-q", "-b", "other", "origin/main")
    line = new_branch_line("feature/ci", reviewed)

    reviewed = pre_push(work, line, monkeypatch)
    reviewed_err = capsys.readouterr().err
    git(work, "checkout", "-q", "feature/ci")
    unreviewed = commit(work, "docs/after.md", "after\n")
    git(work, "checkout", "-q", "other")
    stale = pre_push(work, new_branch_line("feature/ci", unreviewed), monkeypatch)

    assert reviewed == 0, reviewed_err
    assert "scores 1 file(s)" in reviewed_err
    assert stale == 1


def test_incremental_push_after_merging_main_scores_only_branch_files(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC3: an existing remote branch that merged main is not charged for main."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/docs")
    pushed = commit(work, "docs/one.md", "one\n")
    git(work, "push", "-q", "origin", "feature/docs")
    origin.advance_main(WORKFLOW)
    git(work, "fetch", "-q", "origin")
    git(work, "merge", "-q", "--no-edit", "origin/main")
    head = commit(work, "docs/two.md", "two\n")
    # The remote tip to HEAD range, which lefthook uses for an existing
    # branch, carries main's workflow in through the merge.
    assert WORKFLOW in git(work, "diff", "--name-only", pushed, head).splitlines()
    line = f"refs/heads/feature/docs {head} refs/heads/feature/docs {pushed}\n"

    result = pre_push(work, line, monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "refs/heads/feature/docs scores 2 file(s)" in err


def test_incremental_push_rescans_files_from_earlier_pushes(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC3: a new commit moves the branch off its marker, so the marker dies."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/ci")
    commit(work, WORKFLOW, "on: push\n")
    pushed = marker(work)
    git(work, "push", "-q", "origin", "feature/ci")
    head = commit(work, "docs/later.md", "later\n")
    line = f"refs/heads/feature/ci {head} refs/heads/feature/ci {pushed}\n"

    result = pre_push(work, line, monkeypatch)

    err = capsys.readouterr().err
    assert result == 1, err
    assert "scores 2 file(s)" in err


def test_deletion_only_push_scores_nothing_and_says_so(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC4: a deletion carries no commits, and the skip is reported, not silent."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "-b", "feature/gone")
    old = commit(work, WORKFLOW, "on: push\n")
    line = f"(delete) {ZERO} refs/heads/feature/gone {old}\n"

    result = pre_push(work, line, monkeypatch)

    err = capsys.readouterr().err
    assert result == 0, err
    assert "Infrastructure scan: skipped, no branch or tag ref in this push carries commits" in err


def test_missing_origin_main_fails_loud_instead_of_using_local_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC5: no origin/main means no base; local main is not a substitute."""
    hooks = tmp_path / "no-hooks"
    hooks.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q", "-b", "main")
    configure(work, hooks)
    install_scripts(work)
    commit(work, "README.md", "base\n")
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "could not resolve merge-base(origin/main" in err
    assert "scores" not in err


def test_unrelated_history_fails_loud_instead_of_scoring_the_whole_tree(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC5: no merge-base means no base; the empty tree is not a substitute."""
    work = work_clone(origin, tmp_path)
    git(work, "checkout", "-q", "--orphan", "feature/orphan")
    git(work, "rm", "-rq", "--cached", ".")
    head = commit(work, "docs/orphan.md", "orphan\n")

    result = pre_push(work, new_branch_line("feature/orphan", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "could not resolve merge-base(origin/main" in err


def test_missing_detector_fails_the_push(
    origin: Origin,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A detector that cannot run is not a detector that found nothing."""
    work = work_clone(origin, tmp_path, detector=False)
    git(work, "checkout", "-q", "-b", "feature/docs")
    head = commit(work, "docs/note.md", "note\n")

    result = pre_push(work, new_branch_line("feature/docs", head), monkeypatch)

    err = capsys.readouterr().err
    assert result == 2, err
    assert "can't open file" in err
