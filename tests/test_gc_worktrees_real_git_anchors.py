"""Real git regression tests for anchors that live only in the admin directory.

``git worktree remove`` deletes ``.git/worktrees/<name>`` whole. Two kinds of
anchor die with it: refs under ``refs/worktree/`` and the reflogs under
``logs/``. Nothing in the main repository names either, so ``rev-list --not
--all`` reads a commit only one of them holds as unreachable and the next
``gc`` collects it.

Whether git actually protects such a commit is a fact about git, not about this
code, so every test builds the anchor with real git and then asks git. Each
positive case is paired with a control. For the ref cases the control points
the ref at a reachable commit, because a gate that kept every worktree carrying
a local ref would pass the positive case while proving nothing. For the reflog
case the control runs ``gc --prune=now`` with the worktree still in place: a
repro that only collects *after* removing the worktree cannot tell a real loss
channel from an object git was never holding onto.

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
    reason = reason_of(report, worktree)
    assert "git -C " in reason, reason
    assert f"branch gc-rescue-{oid} {oid}" in reason, reason


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
    command = command_of(reason, "git -C ")
    result = subprocess.run(
        # A reader pastes this into a shell, so the test has to run it as one.
        # Spelled as argv so the interpreter is named here rather than inherited
        # from whatever the caller's environment happens to point sh at.
        ["bash", "-c", command],
        cwd=git_sandbox.main,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr

    git(git_sandbox.main, "worktree", "remove", str(worktree))
    git(git_sandbox.main, "gc", "--prune=now")
    assert git(git_sandbox.main, "cat-file", "-t", oid).stdout.strip() == "commit"


def _reflog_only_commit(sandbox: GitSandbox, worktree: Path, name: str) -> str:
    """Leave a commit named only by the reflog of a per-worktree ref.

    ``update-ref --create-reflog`` writes ``logs/refs/worktree/<name>`` in the
    admin directory. Moving the ref afterwards leaves the reflog naming the old
    commit while no ref does. The reflog of ``HEAD`` never sees it, and neither
    does any query run in the main repository.
    """
    lost = git(
        worktree, "commit-tree", "-m", "reflog-only", git(worktree, "write-tree").stdout.strip()
    ).stdout.strip()
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    git(worktree, "update-ref", "--create-reflog", "-m", "create", f"refs/worktree/{name}", lost)
    git(worktree, "update-ref", "-m", "move", f"refs/worktree/{name}", head, lost)
    assert git(sandbox.main, "for-each-ref", "--contains", lost).stdout == ""
    return lost


def test_a_reflog_of_a_worktree_local_ref_is_an_anchor_too(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``logs/HEAD`` is not the only reflog the removal deletes.

    A reader that opened only ``logs/HEAD`` cleared this worktree for removal
    while ``logs/refs/worktree/mywork`` held the sole remaining name for a
    commit. The paired control below shows git really was protecting it.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "anchor-reflog-only"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    lost = _reflog_only_commit(git_sandbox, worktree, "mywork")

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False, decision["reason"]
    reason = reason_of(report, worktree)
    assert "git -C " in reason, reason
    assert f"branch gc-rescue-{lost} {lost}" in reason, reason


def test_that_reflog_really_is_what_keeps_the_commit_alive(
    git_sandbox: GitSandbox,
) -> None:
    """Negative control for the test above, in both directions.

    With the worktree in place the commit survives ``gc --prune=now``, so the
    reflog is a real anchor rather than an object git was going to drop anyway.
    Remove the worktree and the same ``gc`` collects it. A repro that only ran
    the second half would report a loss for an object that was never held.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "anchor-reflog-control"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    lost = _reflog_only_commit(git_sandbox, worktree, "mywork")

    git(git_sandbox.main, "gc", "--prune=now")
    assert git(git_sandbox.main, "cat-file", "-t", lost).stdout.strip() == "commit"

    git(git_sandbox.main, "worktree", "remove", "--force", str(worktree))
    git(git_sandbox.main, "gc", "--prune=now")
    gone = subprocess.run(
        ["git", "cat-file", "-t", lost],
        cwd=git_sandbox.main,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert gone.returncode != 0, "the reflog was not the only anchor after all"
