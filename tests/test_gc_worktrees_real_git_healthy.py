"""Real git regression tests for healthy worktrees that still hold unique work.

Clean, merged, and fully pushed all describe one commit: the worktree's
*current* HEAD. They say nothing about commits the worktree reached and then
left. A worktree can pass every ordinary check and still be the only thing
naming a commit, because its own reflog is that commit's sole anchor and
``git worktree remove`` deletes the reflog along with the admin directory.

The sibling file ``test_gc_worktrees_real_git_stale.py`` covers *which* losses
get reported for an entry whose directory is gone. This file covers the two
things that file does not: worktrees that look entirely healthy and still hold
unique work, and whether the rescue commands the report prints actually run.

Mocks cannot prove any of this. Whether ``for-each-ref --contains`` finds a
commit, whether ``checkout-index`` honours a skip-worktree bit, and whether a
printed rescue command actually runs are facts about git, so each test builds
the condition with real git and then reads the report back.
"""

from __future__ import annotations

import os
import shutil
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
    write_and_commit,
)


def _abandon_commits(sandbox: GitSandbox, worktree: Path, count: int) -> list[str]:
    """Commit ``count`` times in a detached worktree, then move HEAD back off them.

    Each commit is left anchored by nothing but this worktree's own reflog:
    no branch points at it, and HEAD has moved away.
    """
    base = git(worktree, "rev-parse", "HEAD").stdout.strip()
    abandoned = []
    for index in range(count):
        write_and_commit(worktree, f"orphan{index}.txt", f"{index}\n", f"abandoned {index}")
        abandoned.append(git(worktree, "rev-parse", "HEAD").stdout.strip())
        git(worktree, "checkout", "--detach", base)
    for oid in abandoned:
        assert git(sandbox.main, "for-each-ref", "--contains", oid).stdout == ""
    return abandoned


def test_a_clean_merged_worktree_is_kept_when_its_reflog_is_a_commits_only_anchor(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The worktree passes every ordinary check and still holds unique work.

    Its directory is present, its tree is clean, and its HEAD is an ancestor of
    the base. Nothing about those three facts covers the commit it made and
    then walked away from, which only its reflog names.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-detached"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    [orphan] = _abandon_commits(git_sandbox, worktree, 1)

    assert worktree.is_dir()
    assert git(worktree, "status", "--porcelain").stdout == ""

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is False, decision["reason"]
    reason = reason_of(report, worktree)
    assert "git -C " in reason, reason
    assert f"branch gc-rescue-{orphan} {orphan}" in reason, reason


def test_a_clean_merged_worktree_with_nothing_at_risk_is_still_removed(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Negative control: the reflog gate must not keep every worktree.

    Same shape as the test above minus the abandoned commit. If this one also
    came back as a keep, the gate would be answering "unknown" for everything
    and the positive case above would prove nothing.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-plain"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["remove"] is True, decision["reason"]
    assert "gc-rescue-" not in reason_of(report, worktree)


def test_the_printed_rescue_command_runs_verbatim_for_several_commits(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two abandoned commits must yield two commands, not one invalid one.

    Joining with a space produced ``git branch a A git branch b B``, which git
    reads as one call with four arguments and rejects. The test pastes what the
    report printed into a shell and requires both branches to exist after.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-two-orphans"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    first, second = _abandon_commits(git_sandbox, worktree, 2)

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    command = command_of(reason, "git -C ")
    assert command.count("branch gc-rescue-") == 2, command

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
    for oid in (first, second):
        assert git(git_sandbox.main, "rev-parse", f"gc-rescue-{oid}").stdout.strip() == oid


def test_the_index_recovery_command_exports_a_skip_worktree_entry(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """``checkout-index -a`` silently skips entries carrying the skip-worktree bit.

    The entry here is stale, because the index warning is what the stale path
    prints. The bug is in the command text, not in when it fires.

    It exports the other files, exits 0, and says nothing about the one it left
    behind, so the report would claim a recovery that did not happen. The fix
    is ``--ignore-skip-worktree-bits``; this test proves the printed command
    carries it and that the blob comes back.
    """
    worktree = git_sandbox.root / "skip-worktree-index"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "HEAD")
    (worktree / "staged.txt").write_text("unique staged blob\n", encoding="utf-8")
    git(worktree, "add", "staged.txt")
    git(worktree, "update-index", "--skip-worktree", "staged.txt")
    shutil.rmtree(worktree)

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert "--ignore-skip-worktree-bits" in reason, reason

    command = command_of(reason, "mkdir -p RECOVERY_DIR", tmp_path / "recovery")
    result = subprocess.run(
        # A reader pastes this into a shell, so the test has to run it as one.
        # Spelled as argv so the interpreter is named here rather than inherited
        # from whatever the caller's environment happens to point sh at.
        ["bash", "-c", command],
        cwd=tmp_path,  # outside any repo: the printed command has to carry its own -C
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    recovered = tmp_path / "recovery"
    assert (recovered / "staged.txt").read_text(encoding="utf-8") == "unique staged blob\n"
    assert (recovered / "index").exists(), "the copied index is the half that recovers the rest"


def test_the_index_recovery_command_preserves_unmerged_stages(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """``checkout-index -a`` writes nothing for an unmerged entry and still exits 0.

    A conflicted index holds three blobs per path and no stage-0 entry, so the
    export produces an empty directory and reports success. A reader pasting
    the old command saw exit 0 and believed the staged work was rescued while
    every stage went with the removal. The copied index is what carries them.
    """
    worktree = git_sandbox.root / "unmerged-index"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "HEAD")
    git(worktree, "checkout", "-b", "gc-left")
    (worktree / "conflict.txt").write_text("left side\n", encoding="utf-8")
    git(worktree, "add", "conflict.txt")
    git(worktree, "commit", "-m", "left")
    git(worktree, "checkout", "--detach", "HEAD~1")
    (worktree / "conflict.txt").write_text("right side\n", encoding="utf-8")
    git(worktree, "add", "conflict.txt")
    git(worktree, "commit", "-m", "right")
    merge = git(worktree, "merge", "gc-left", check=False)
    assert merge.returncode != 0, "the merge has to conflict for the index to hold stages"
    assert git(worktree, "ls-files", "-u").stdout.strip(), "no unmerged stages were staged"
    shutil.rmtree(worktree)

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    command = command_of(reason, "mkdir -p RECOVERY_DIR", tmp_path / "recovery")
    result = subprocess.run(
        # A reader pastes this into a shell, so the test has to run it as one.
        # Spelled as argv so the interpreter is named here rather than inherited
        # from whatever the caller's environment happens to point sh at.
        ["bash", "-c", command],
        cwd=tmp_path,  # outside any repo: the printed command has to carry its own -C
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "recovery" / "conflict.txt").exists(), (
        "checkout-index is expected to skip it; the point is that the copy does not"
    )
    stages = subprocess.run(
        ["git", "ls-files", "-s", "-u"],
        cwd=git_sandbox.main,
        env={**os.environ, "GIT_INDEX_FILE": str(tmp_path / "recovery" / "index")},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert "conflict.txt" in stages.stdout, stages.stdout
    assert stages.stdout.count("conflict.txt") >= 2, "both sides of the conflict must survive"


def test_the_index_recovery_command_preserves_a_gitlink(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """``checkout-index -a`` writes a submodule entry as an empty directory.

    The recorded commit is the whole content of a gitlink, and the export
    keeps none of it while exiting 0. A reader who saw the directory appear
    would conclude the submodule came back. Only the copied index still names
    the commit the entry pointed at.
    """
    worktree = git_sandbox.root / "gitlink-index"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "HEAD")
    pointed_at = git(worktree, "rev-parse", "HEAD").stdout.strip()
    git(worktree, "update-index", "--add", "--cacheinfo", f"160000,{pointed_at},sub")
    shutil.rmtree(worktree)

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    command = command_of(reason, "mkdir -p RECOVERY_DIR", tmp_path / "recovery")
    result = subprocess.run(
        # A reader pastes this into a shell, so the test has to run it as one.
        # Spelled as argv so the interpreter is named here rather than inherited
        # from whatever the caller's environment happens to point sh at.
        ["bash", "-c", command],
        cwd=tmp_path,  # outside any repo: the printed command has to carry its own -C
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert list((tmp_path / "recovery" / "sub").iterdir()) == [], (
        "checkout-index is expected to empty it; the point is that the copy is not empty"
    )
    entries = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=git_sandbox.main,
        env={**os.environ, "GIT_INDEX_FILE": str(tmp_path / "recovery" / "index")},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert f"160000 {pointed_at} 0\tsub" in entries.stdout, entries.stdout


def test_a_failing_rescue_stops_the_chain_and_shows_in_the_exit_code(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Joined with ``;`` a failed rescue is invisible: the chain runs on and exits 0.

    ``git branch`` refuses a name that already exists, which is the realistic
    failure after a partial earlier attempt. The reader needs the chain to stop
    there, because continuing means the report says the rescue succeeded while
    one commit stayed unanchored. A shell reports the status of the last
    command in a ``;`` list, so only ``&&`` surfaces it.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-blocked-rescue"
    git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    first, second = _abandon_commits(git_sandbox, worktree, 2)

    reason = reason_of(run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    command = command_of(reason, "git -C ")
    blocked = command.split(" branch ", 1)[1].split()[0]
    survivor = second if blocked.endswith(first) else first
    git(git_sandbox.main, "branch", blocked, head)

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
    assert result.returncode != 0, "a blocked rescue that exits 0 reads as a completed rescue"
    assert (
        git(
            git_sandbox.main, "rev-parse", "--verify", f"gc-rescue-{survivor}", check=False
        ).returncode
        != 0
    ), "the chain must stop at the failure rather than carry on past it"


def test_a_worktree_on_a_merged_branch_is_kept_when_its_reflog_is_a_commits_only_anchor(
    git_sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The branch path has to ask the same question the detached path asks.

    Merged and fully pushed both describe where the branch points now. A
    worktree that committed and reset still has that commit anchored by
    nothing but its own reflog, and this is the most-travelled path in the
    tool, so a removal here is the likeliest way to lose work.
    """
    head = git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-merged-branch-orphan"
    git(git_sandbox.main, "worktree", "add", "-b", "gc-merged-branch", str(worktree), head)
    write_and_commit(worktree, "orphan.txt", "x\n", "abandoned on a branch")
    abandoned = git(worktree, "rev-parse", "HEAD").stdout.strip()
    git(worktree, "reset", "--hard", head)
    assert git(git_sandbox.main, "for-each-ref", "--contains", abandoned).stdout == ""

    report = run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = decision_for(report, worktree)
    assert decision["branch"] == "gc-merged-branch", decision
    reason = decision["reason"]
    assert isinstance(reason, str), decision
    assert decision["remove"] is False, reason
    assert abandoned in reason, reason
