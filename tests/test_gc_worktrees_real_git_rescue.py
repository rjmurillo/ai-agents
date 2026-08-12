"""Real git coverage for the rescue commands a stale entry's report prints.

The report tells an operator to clear a stale entry, and the entry can be the
only anchor for a detached HEAD, for blobs staged into its orphaned index, and
for commits its own reflog names. Each needs its own rescue command, so the
report prints commands rather than advice.

A printed command is only worth what it does when pasted. These tests build the
loss with real git, take the slice a reader would copy, and run it in a shell
from a directory outside any repository, which is where a bare ``git branch``
fails while still reading as the printed rescue. The probes behind the report
are tested in ``test_gc_worktrees_real_git_stale.py``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.maintenance import worktree_report
from tests.gc_real_git import (
    GitSandbox,
    command_of,
    decision_for,
    git,
    reason_of,
    run_gc_json,
    write_and_commit,
)


def test_all_three_loss_channels_are_reported_together(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One stale entry can abandon HEAD, an index, and a reflog commit at once.

    Rescuing HEAD rescues neither of the others: the reflog commit is not an
    ancestor of HEAD, and the staged blob is in no commit at all. Reporting
    only the loudest channel is what makes a single-reason message dangerous
    rather than merely terse.
    """
    base = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "three-losses"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), base)
    write_and_commit(worktree, "a.txt", "chain a\n", "chain A")
    abandoned = git(worktree, "rev-parse", "HEAD").stdout.strip()
    git(worktree, "checkout", "--detach", base)
    write_and_commit(worktree, "b.txt", "chain b\n", "chain B")
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    (worktree / "staged.txt").write_text("only staged\n", encoding="utf-8")
    git(worktree, "add", "staged.txt")
    shutil.rmtree(worktree)

    assert git(git_sandbox.main, "for-each-ref", "--contains", head).stdout == ""
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", abandoned, head],
        cwd=git_sandbox.main,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert ancestor.returncode != 0, "the abandoned commit must not be reachable from HEAD"

    report = run_gc_json(git_sandbox, monkeypatch, capsys)
    reason = decision_for(report, worktree)["reason"]
    assert isinstance(reason, str)

    assert f"branch gc-rescue-{head} {head}" in reason, reason
    assert f"branch gc-rescue-{abandoned} {abandoned}" in reason, reason
    assert "checkout-index" in reason, reason
    assert f"{head}." not in reason, "a trailing period turns the sha into a bad object"


def _cwd_outside_any_repository(candidate: Path) -> Path:
    """A directory that is not inside any git repository, for -C regression tests.

    The sandbox lives under ``.pytest_tmp`` inside this project's own checkout,
    so a path there is inside a repository and a bare ``git branch`` would run
    against the wrong one rather than fail. ``tmp_path`` sits under the system
    temp directory instead; this confirms git sees no repository there before
    handing it back, so a regression to a bare command fails loudly.
    """
    assert git(candidate, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0, (
        "the chosen cwd is inside a repository, so it cannot prove what -C buys"
    )
    return candidate


def test_the_reflog_rescue_command_runs_from_outside_any_repository(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The admin rescue names the repo with ``-C``, so it works from any cwd.

    A reader pastes the printed command wherever they happen to stand, and that
    is often not inside a repository. A bare ``git branch`` fails there with
    ``not a git repository`` while reading as the printed rescue, so the commit
    it claimed to save stays lost. Running it from a non-repo cwd is what proves
    the ``-C`` prefix is load-bearing rather than decorative.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "reflog-outside-cwd"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    write_and_commit(worktree, "orphan.txt", "only in the reflog\n", "abandoned")
    orphan = git(worktree, "rev-parse", "HEAD").stdout.strip()
    git(worktree, "checkout", "--detach", head)
    shutil.rmtree(worktree)

    assert git(git_sandbox.main, "for-each-ref", "--contains", orphan).stdout == ""

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    command = command_of(reason, "git -C ")
    outside = _cwd_outside_any_repository(tmp_path)
    result = subprocess.run(
        # A reader pastes this into a shell, so the test has to run it as one.
        # Spelled as argv so the interpreter is named here rather than inherited
        # from whatever the caller's environment happens to point sh at.
        ["bash", "-c", command],
        cwd=outside,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert git(git_sandbox.main, "rev-parse", f"gc-rescue-{orphan}").stdout.strip() == orphan


def test_the_head_rescue_command_runs_from_outside_any_repository(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """The detached-HEAD rescue is ``-C`` pinned too, not only the admin one.

    ``_head_warning`` builds its own rescue command, so the ``-C`` fix has to
    reach it independently. A stale entry whose HEAD no ref contains prints that
    command first; running it from a directory outside any repository proves it
    creates the branch in the repository that still holds the commit.
    """
    base = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "unreachable-head-outside-cwd"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), base)
    write_and_commit(worktree, "gone.txt", "walked away from\n", "unreachable head")
    head = git(worktree, "rev-parse", "HEAD").stdout.strip()
    shutil.rmtree(worktree)

    assert git(git_sandbox.main, "for-each-ref", "--contains", head).stdout == ""

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert worktree_report.KEEP_STALE_UNREACHABLE in reason, reason
    command = command_of(reason, "git -C ")
    assert f"branch gc-rescue-{head} {head}" in command, command
    outside = _cwd_outside_any_repository(tmp_path)
    result = subprocess.run(
        # A reader pastes this into a shell, so the test has to run it as one.
        # Spelled as argv so the interpreter is named here rather than inherited
        # from whatever the caller's environment happens to point sh at.
        ["bash", "-c", command],
        cwd=outside,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert git(git_sandbox.main, "rev-parse", f"gc-rescue-{head}").stdout.strip() == head


def test_the_rescue_chain_stays_runnable_when_more_orphans_are_counted_after_it(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Past three orphans the reason gains prose, and the paste must survive it.

    The rescue chain prints the first three commits and then says how many more
    the admin directory holds. Appended straight onto the last SHA that sentence
    became part of what a reader copies, and ``bash`` rejects the unescaped
    ``(`` before running a single rescue, so the note about the commits still at
    risk was what stopped the first three from being saved. Five orphans is the
    smallest build that produces both halves, and running the slice is the only
    assertion that can tell a delimiter from a decoration.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "many-orphans-outside-cwd"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    orphans = []
    for index in range(5):
        write_and_commit(worktree, f"orphan{index}.txt", f"abandoned {index}\n", f"orphan {index}")
        orphans.append(git(worktree, "rev-parse", "HEAD").stdout.strip())
        git(worktree, "checkout", "--detach", head)
    shutil.rmtree(worktree)

    for orphan in orphans:
        assert git(git_sandbox.main, "for-each-ref", "--contains", orphan).stdout == ""

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert "2 more are named under" in reason, reason
    command = command_of(reason, "git -C ")
    assert "more are named under" not in command, command

    outside = _cwd_outside_any_repository(tmp_path)
    result = subprocess.run(
        # A reader pastes this into a shell, so the test has to run it as one.
        # Spelled as argv so the interpreter is named here rather than inherited
        # from whatever the caller's environment happens to point sh at.
        ["bash", "-c", command],
        cwd=outside,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    rescued = [
        orphan
        for orphan in orphans
        if git(
            git_sandbox.main, "rev-parse", "--verify", f"gc-rescue-{orphan}", check=False
        ).returncode
        == 0
    ]
    assert len(rescued) == 3, rescued
