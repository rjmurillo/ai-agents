"""Real git regression tests for worktree garbage collection: merge status.

These build an actual repository with actual worktrees and run the real tool
over it, because the safety contract is about what git reports, not about what
a mock was told to report. A squash merge in particular breaks patch-id
equivalence, so ``git cherry`` cannot see it and only a real repository proves
the detection works.

The stale-entry cases, where a worktree's directory is gone and its admin
record is all that is left, live in ``test_gc_worktrees_real_git_stale.py``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.maintenance import gc_worktrees
from tests.gc_real_git import GitSandbox, decision_for, git, run_gc_json, write_and_commit


def _add_worktree_branch(sandbox: GitSandbox, branch: str) -> Path:
    worktree = sandbox.root / branch.replace("/", "-")
    git(sandbox.main, "worktree", "add", "-b", branch, str(worktree))
    return worktree


def _create_squash_merged_branch(sandbox: GitSandbox, branch: str = "feat/squash") -> Path:
    worktree = _add_worktree_branch(sandbox, branch)
    write_and_commit(worktree, "feature.txt", f"{branch}\n", "feature")
    git(worktree, "push", "-u", "origin", branch)
    git(sandbox.main, "merge", "--squash", branch)
    git(sandbox.main, "commit", "-m", "squash feature")
    git(sandbox.main, "push", "origin", "main")
    git(sandbox.main, "push", "origin", f":{branch}")
    git(sandbox.main, "fetch", "--prune", "origin")
    return worktree


def test_squash_merged_branch_with_deleted_origin_head_is_removable(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _create_squash_merged_branch(git_sandbox)

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is True
    assert decision["reason"] == "merged by deleted upstream"


def test_unmerged_unpushed_branch_with_existing_origin_head_is_kept(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _add_worktree_branch(git_sandbox, "feat/unmerged")
    write_and_commit(worktree, "published.txt", "published\n", "published")
    git(worktree, "push", "-u", "origin", "feat/unmerged")
    write_and_commit(worktree, "local.txt", "local\n", "local")

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False
    assert decision["reason"] == gc_worktrees.KEEP_UNPUSHED


def test_clean_detached_ancestor_worktree_is_removable(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = git_sandbox.root / "detached-main"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "origin/main")

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["branch"] is None
    assert decision["remove"] is True
    assert decision["reason"] == "merged to base"


def test_dirty_squash_merged_branch_is_kept(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _create_squash_merged_branch(git_sandbox, "feat/dirty")
    (worktree / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False
    assert decision["reason"] == gc_worktrees.KEEP_DIRTY


def test_remote_head_failure_uses_ancestry_only_behavior(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _create_squash_merged_branch(git_sandbox, "feat/offline")
    git(git_sandbox.main, "remote", "set-url", "origin", str(git_sandbox.root / "missing"))

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert report["remote_head_lookup_failed"] is True
    assert decision["remove"] is False
    assert decision["reason"] == gc_worktrees.KEEP_UNPUSHED

    code = gc_worktrees.main([])
    captured = capsys.readouterr()
    assert code == 0
    assert "remote head lookup failed, using ancestry-only merge checks" in captured.out


def test_squash_detection_is_load_bearing_negative_control(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _create_squash_merged_branch(git_sandbox, "feat/control")

    with patch(
        "scripts.maintenance.gc_worktrees._gc_remote.is_merged_by_deleted_upstream",
        return_value=False,
    ):
        report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False
    assert decision["reason"] == gc_worktrees.KEEP_UNPUSHED
