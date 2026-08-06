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

import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.maintenance import _gc_apply, gc_worktrees


@dataclass(frozen=True, slots=True)
class GitSandbox:
    """A disposable repository with an origin remote and linked worktrees."""

    root: Path
    main: Path
    remote: Path


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _write_and_commit(cwd: Path, relative_path: str, content: str, message: str) -> str:
    (cwd / relative_path).write_text(content, encoding="utf-8")
    _git(cwd, "add", relative_path)
    _git(cwd, "commit", "-m", message)
    return _git(cwd, "rev-parse", "HEAD")


@pytest.fixture
def git_sandbox() -> Iterator[GitSandbox]:
    temp_parent = Path(__file__).resolve().parents[1] / ".pytest_tmp" / "gc_worktrees"
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gc-apply-", dir=temp_parent) as temp_dir:
        root = Path(temp_dir)
        remote = root / "origin.git"
        main = root / "repo"
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(remote)],
            check=True,
            capture_output=True,
        )
        subprocess.run(["git", "clone", str(remote), str(main)], check=True, capture_output=True)
        for key, value in (
            ("user.email", "test@example.com"),
            ("user.name", "Test User"),
            ("commit.gpgsign", "false"),
        ):
            _git(main, "config", key, value)
        _write_and_commit(main, "base.txt", "base\n", "base")
        _git(main, "push", "-u", "origin", "main")
        yield GitSandbox(root=root, main=main, remote=remote)


def _merged_candidate(sandbox: GitSandbox, name: str) -> Path:
    """A worktree that every ordinary check calls safe to remove."""
    worktree = sandbox.root / name
    _git(sandbox.main, "worktree", "add", "--detach", str(worktree), "main")
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
    if _git(sandbox.main, "cat-file", "-t", commit) != "commit":
        return False
    return _git(sandbox.main, "for-each-ref", "--contains", commit) == ""


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
        landed.append(_write_and_commit(worktree, "late.txt", "late\n", "late"))

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
    before = _git(worktree, "rev-parse", "HEAD")
    stranded: list[str] = []

    def commit_and_reset() -> None:
        stranded.append(_write_and_commit(worktree, "gone.txt", "gone\n", "gone"))
        _git(worktree, "reset", "--hard", before)

    report = _apply_with(git_sandbox, monkeypatch, commit_and_reset)

    assert stranded, "the interference hook never ran"
    assert _git(worktree, "rev-parse", "HEAD") == before, "HEAD must be back where it started"
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
