"""Real git regression tests for anchors that live only in the admin directory.

``git worktree remove`` deletes ``.git/worktrees/<name>`` whole, and a ref
under ``refs/worktree/`` dies with it. Nothing in the main repository names
that ref, so ``rev-list --not --all`` reads a commit only it holds as
unreachable and the next ``gc`` collects it.

Whether git actually protects such a commit is a fact about git, not about this
code, so every test builds the anchor with real git and then asks git. Each
positive case is paired with a control that should *not* block removal, because
a gate that kept every worktree carrying a local ref would pass the positive
case while proving nothing.

Split out of ``test_gc_worktrees_real_git_healthy.py``, which covers a
different question: worktrees that look healthy by every ordinary check and
still hold unique work.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.gc_real_git import (
    GitSandbox,
    command_of,
    decision_for,
    git,
    reason_of,
    run_gc_json,
)


def _worktree_local_ref(sandbox: GitSandbox, worktree: Path, name: str) -> str:
    """Anchor a fresh commit under this worktree's own ``refs/worktree/`` namespace.

    ``commit-tree`` writes no reflog entry, so the reflog probe cannot see this
    commit. ``refs/worktree/`` is per-worktree and lives in the admin directory,
    so ``rev-list --not --all`` in the main repository cannot see it either.
    That leaves the admin directory as the sole anchor.
    """
    oid = git(
        worktree, "commit-tree", "-m", "worktree-local", git(worktree, "write-tree").stdout.strip()
    ).stdout.strip()
    git(worktree, "update-ref", f"refs/worktree/{name}", oid)
    assert git(sandbox.main, "for-each-ref", "--contains", oid).stdout == ""
    return oid


def test_a_worktree_local_ref_is_an_anchor_the_reflog_cannot_see(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A commit held only by ``refs/worktree/`` dies with the admin directory.

    The reflog probe alone reports this worktree as safe, because ``commit-tree``
    writes nothing to ``logs/HEAD``. Verified against real git 2.43.0: after
    ``git worktree remove`` the commit shows up under ``fsck --unreachable`` and
    ``git gc --prune=now`` collects it.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-local-ref"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    oid = _worktree_local_ref(git_sandbox, worktree, "mywork")

    assert git(worktree, "status", "--porcelain").stdout == ""

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False, decision["reason"]
    assert f"git branch gc-rescue-{oid} {oid}" in reason_of(report, worktree)


def test_a_worktree_local_ref_on_a_reachable_commit_does_not_block_removal(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Negative control: the gate reads reachability, not the mere presence of a ref.

    Same ``refs/worktree/`` entry as the test above, pointed at a commit the
    base branch already contains. A gate that kept every worktree carrying a
    local ref would pass the positive case while proving nothing.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-local-ref-reachable"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    git(worktree, "update-ref", "refs/worktree/mywork", head)

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is True, decision["reason"]
    assert "gc-rescue-" not in reason_of(report, worktree)


def test_the_printed_rescue_saves_a_commit_only_a_worktree_local_ref_held(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the printed command, then destroy the anchor, and check the commit lives.

    Printing a rescue that does not rescue is worse than printing nothing, so
    this runs the command verbatim and then does what the reader was warned
    about: removes the worktree and collects.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-local-ref-rescue"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    oid = _worktree_local_ref(git_sandbox, worktree, "mywork")

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    command = command_of(reason, "git branch gc-rescue-")
    result = subprocess.run(
        # A reader pastes this into a shell, so the test has to run it as one.
        # Spelled as argv so the interpreter is named here rather than inherited
        # from whatever the caller's environment happens to point sh at.
        ["bash", "-c", command],
        cwd=git_sandbox.main,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr

    git(git_sandbox.main, "worktree", "remove", str(worktree))
    git(git_sandbox.main, "gc", "--prune=now")
    assert git(git_sandbox.main, "cat-file", "-t", oid).stdout.strip() == "commit"
