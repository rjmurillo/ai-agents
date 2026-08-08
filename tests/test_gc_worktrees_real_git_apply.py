"""Real git regression tests for the window between planning and removing.

``--apply`` re-reads the repository before it mutates anything, so the plan a
reader reviewed is never the plan that runs. Two ways of committing inside
that window survive a comparison of HEAD against HEAD, and both were found by
adversarial review after the comparison was already in place.

The first commits between the recheck deciding a candidate is safe and the
recheck's HEADs being recorded. The new commit becomes the baseline, so it
compares equal to itself and the removal proceeds.

The second commits and goes back. Check out a branch, commit, reset: HEAD ends
where it started while the commit survives with nothing but that worktree's
own reflog naming it, and any comparison of HEAD against HEAD passes.

A mock proves neither. Whether ``git worktree remove`` refuses, whether the
commit survives in the object database, and whether any ref still reaches it
are facts about git, so each test builds the race with real git and then reads
the object database back.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.maintenance import _gc_apply, gc_worktrees
from tests.gc_real_git import GitSandbox, git, write_and_commit


def _merged_candidate(sandbox: GitSandbox, name: str) -> Path:
    """A worktree that every ordinary check calls safe to remove."""
    worktree = sandbox.root / name
    git(sandbox.main, "worktree", "add", "--detach", str(worktree), "main")
    return worktree


def _apply_with(
    sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    interfere: Callable[[], None],
) -> gc_worktrees.GcReport:
    """Build a plan, run ``interfere`` inside the apply window, then apply.

    The hook fires after ``revalidate`` returns and before ``apply_removals``
    records the HEADs it will compare against, which is the exact window the
    comparison cannot see into.
    """
    monkeypatch.chdir(sandbox.main)
    report = gc_worktrees.build_report("origin/main", apply=True)

    def revalidate() -> gc_worktrees.GcReport:
        fresh = gc_worktrees.build_report("origin/main", apply=True)
        interfere()
        return fresh

    _gc_apply.apply_removals(report, revalidate, gc_worktrees._run_git)
    return report


def _unreachable(sandbox: GitSandbox, commit: str) -> bool:
    """Does the object survive with no ref reaching it?"""
    if git(sandbox.main, "cat-file", "-t", commit).stdout.strip() != "commit":
        return False
    return git(sandbox.main, "for-each-ref", "--contains", commit).stdout.strip() == ""


def test_a_commit_landing_inside_the_apply_window_is_not_removed(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The commit that becomes its own baseline.

    Committing after the recheck decided the candidate is safe, but before the
    HEADs it will be compared against are read, makes the new commit the
    expected value. It then compares equal to itself, the removal proceeds, and
    the only thing that named the commit goes with the admin directory.
    """
    worktree = _merged_candidate(git_sandbox, "racer")
    landed: list[str] = []

    def commit_inside_the_window() -> None:
        landed.append(write_and_commit(worktree, "late.txt", "late\n", "late"))

    report = _apply_with(git_sandbox, monkeypatch, commit_inside_the_window)

    assert landed, "the interference hook never ran"
    assert str(worktree) not in report.removed, report.remove_errors
    assert _unreachable(git_sandbox, landed[0]), "the late commit must still be in the odb"
    assert any(str(worktree) in error for error in report.remove_errors), report.remove_errors


def test_a_worktree_that_commits_and_goes_back_is_not_removed(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HEAD ends where it started and the commit still survives.

    This is the case a HEAD comparison cannot catch by construction: the value
    it compares is identical before and after. Only asking whether the reflog
    is now the sole anchor for something finds it.
    """
    worktree = _merged_candidate(git_sandbox, "aba")
    before = git(worktree, "rev-parse", "HEAD").stdout.strip()
    stranded: list[str] = []

    def commit_and_reset() -> None:
        stranded.append(write_and_commit(worktree, "gone.txt", "gone\n", "gone"))
        git(worktree, "reset", "--hard", before)

    report = _apply_with(git_sandbox, monkeypatch, commit_and_reset)

    assert stranded, "the interference hook never ran"
    assert git(worktree, "rev-parse", "HEAD").stdout.strip() == before, (
        "HEAD must be back where it started"
    )
    assert str(worktree) not in report.removed, report.remove_errors
    assert _unreachable(git_sandbox, stranded[0]), "the stranded commit must still be in the odb"


def test_a_candidate_with_nothing_stranded_is_still_removed(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative control, so the two guards above are not just refusing.

    Without this, both tests pass equally well against an ``apply_removals``
    that removes nothing at all.
    """
    worktree = _merged_candidate(git_sandbox, "quiet")

    report = _apply_with(git_sandbox, monkeypatch, lambda: None)

    assert report.removed == [str(worktree)], report.remove_errors
    assert report.remove_errors == []
    assert not worktree.exists()


def test_a_merge_started_inside_the_apply_window_is_not_removed(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The third way through the window, and the one both earlier guards miss.

    ``git merge --no-commit --no-ff`` against a parent whose tree matches HEAD
    moves no HEAD, so the comparison passes, and writes no reflog entry, so the
    reflog probe passes. ``MERGE_HEAD`` is the only thing reaching the other
    parent, and it lives in the directory the removal deletes.

    The merge is started after ``revalidate`` returns, so the decision path
    never sees it and only the per-candidate probe can.
    """
    worktree = _merged_candidate(git_sandbox, "window-merge")
    stranded: list[str] = []

    def interfere() -> None:
        other = git(
            worktree, "commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "orphan"
        ).stdout.strip()
        git(worktree, "merge", "--no-commit", "--no-ff", other, check=False)
        stranded.append(other)

    report = _apply_with(git_sandbox, monkeypatch, interfere)

    assert str(worktree) not in report.removed, report.removed
    assert any("unfinished merge" in error for error in report.remove_errors), report.remove_errors
    survives = git(git_sandbox.main, "cat-file", "-e", stranded[0], check=False)
    assert survives.returncode == 0, "the commit the merge held is still in the object database"


def test_the_window_probe_still_removes_an_untouched_candidate(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative control for the probe added to the removal loop.

    A probe that refused unconditionally would satisfy the test above and stop
    the tool removing anything at all.
    """
    worktree = _merged_candidate(git_sandbox, "window-untouched")
    report = _apply_with(git_sandbox, monkeypatch, lambda: None)

    assert str(worktree) in report.removed, report.remove_errors
    assert not worktree.exists()


def test_a_checkout_swapped_for_another_inside_the_window_is_not_removed(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identity window a HEAD comparison cannot see.

    A HEAD that reads the same value can still belong to a different checkout.
    Delete the candidate and move another worktree that sits at the same commit
    onto its path: ``git rev-parse HEAD`` there answers the recorded value, the
    reflog probe reads the intruder's clean reflog, and no operation is running,
    so every earlier guard passes. Only re-reading whether the marker still
    points back at this entry withholds the removal, which is what keeps
    ``git worktree remove`` from deleting the checkout that moved in.

    The intruder is locked so it is never itself a candidate, which isolates the
    identity probe from the removal of a second entry.
    """
    victim = _merged_candidate(git_sandbox, "swap-victim")
    intruder = _merged_candidate(git_sandbox, "swap-intruder")
    git(git_sandbox.main, "worktree", "lock", str(intruder))

    def swap() -> None:
        shutil.rmtree(victim)
        shutil.move(str(intruder), str(victim))

    report = _apply_with(git_sandbox, monkeypatch, swap)

    assert report.removed == [], report.removed
    assert any(
        str(victim) in error and "no longer the one registered" in error
        for error in report.remove_errors
    ), report.remove_errors
    assert (victim / ".git").is_file(), "the checkout that moved in must still be there"
