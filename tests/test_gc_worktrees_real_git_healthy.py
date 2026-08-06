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

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts.maintenance import gc_worktrees


@dataclass(frozen=True, slots=True)
class GitSandbox:
    """A disposable repository with an origin remote and linked worktrees."""

    root: Path
    main: Path
    remote: Path


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _write_and_commit(cwd: Path, relative_path: str, content: str, message: str) -> None:
    path = cwd / relative_path
    path.write_text(content, encoding="utf-8")
    _git(cwd, "add", relative_path)
    _git(cwd, "commit", "-m", message)


@pytest.fixture
def git_sandbox() -> Iterator[GitSandbox]:
    temp_parent = Path(__file__).resolve().parents[1] / ".pytest_tmp" / "gc_worktrees"
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gc-healthy-", dir=temp_parent) as temp_dir:
        root = Path(temp_dir)
        remote = root / "origin.git"
        main = root / "repo"
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(remote)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "clone", str(remote), str(main)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        _git(main, "config", "user.email", "test@example.com")
        _git(main, "config", "user.name", "Test User")
        _git(main, "config", "commit.gpgsign", "false")
        _write_and_commit(main, "base.txt", "base\n", "base")
        _git(main, "push", "-u", "origin", "main")
        yield GitSandbox(root=root, main=main, remote=remote)


def _run_gc_json(
    sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    monkeypatch.chdir(sandbox.main)
    code = gc_worktrees.main(["--json"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    return json.loads(captured.out)


def _decision_for(report: dict[str, object], path: Path) -> dict[str, object]:
    decisions = report["decisions"]
    assert isinstance(decisions, list)
    matches = [d for d in decisions if isinstance(d, dict) and d["path"] == str(path)]
    assert len(matches) == 1
    return matches[0]


def _reason_of(report: dict[str, object], path: Path) -> str:
    reason = _decision_for(report, path)["reason"]
    assert isinstance(reason, str)
    return reason


def _abandon_commits(sandbox: GitSandbox, worktree: Path, count: int) -> list[str]:
    """Commit ``count`` times in a detached worktree, then move HEAD back off them.

    Each commit is left anchored by nothing but this worktree's own reflog:
    no branch points at it, and HEAD has moved away.
    """
    base = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    abandoned = []
    for index in range(count):
        _write_and_commit(worktree, f"orphan{index}.txt", f"{index}\n", f"abandoned {index}")
        abandoned.append(_git(worktree, "rev-parse", "HEAD").stdout.strip())
        _git(worktree, "checkout", "--detach", base)
    for oid in abandoned:
        assert _git(sandbox.main, "for-each-ref", "--contains", oid).stdout == ""
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
    head = _git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-detached"
    _git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    [orphan] = _abandon_commits(git_sandbox, worktree, 1)

    assert worktree.is_dir()
    assert _git(worktree, "status", "--porcelain").stdout == ""

    report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert decision["remove"] is False, decision["reason"]
    reason = _reason_of(report, worktree)
    assert f"git branch gc-rescue-{orphan} {orphan}" in reason, reason


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
    head = _git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-plain"
    _git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)

    report = _run_gc_json(git_sandbox, monkeypatch, capsys)

    decision = _decision_for(report, worktree)
    assert decision["remove"] is True, decision["reason"]
    assert "gc-rescue-" not in _reason_of(report, worktree)


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
    head = _git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-two-orphans"
    _git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    first, second = _abandon_commits(git_sandbox, worktree, 2)

    reason = _reason_of(_run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    start = reason.index("git branch gc-rescue-")
    end = reason.find(" |", start)
    command = reason[start:] if end == -1 else reason[start:end]
    assert command.count("git branch") == 2, command

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
        assert _git(git_sandbox.main, "rev-parse", f"gc-rescue-{oid}").stdout.strip() == oid


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
    _git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "HEAD")
    (worktree / "staged.txt").write_text("unique staged blob\n", encoding="utf-8")
    _git(worktree, "add", "staged.txt")
    _git(worktree, "update-index", "--skip-worktree", "staged.txt")
    shutil.rmtree(worktree)

    reason = _reason_of(_run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    assert "--ignore-skip-worktree-bits" in reason, reason

    start = reason.index("GIT_INDEX_FILE=")
    end = reason.find(" |", start)
    command = (reason[start:] if end == -1 else reason[start:end]).replace(
        "RECOVERY_DIR", str(tmp_path)
    )
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
    assert (tmp_path / "staged.txt").read_text(encoding="utf-8") == "unique staged blob\n"
    assert (tmp_path / "index").exists(), "the copied index is the half that recovers the rest"


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
    _git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "HEAD")
    _git(worktree, "checkout", "-b", "gc-left")
    (worktree / "conflict.txt").write_text("left side\n", encoding="utf-8")
    _git(worktree, "add", "conflict.txt")
    _git(worktree, "commit", "-m", "left")
    _git(worktree, "checkout", "--detach", "HEAD~1")
    (worktree / "conflict.txt").write_text("right side\n", encoding="utf-8")
    _git(worktree, "add", "conflict.txt")
    _git(worktree, "commit", "-m", "right")
    merge = _git(worktree, "merge", "gc-left", check=False)
    assert merge.returncode != 0, "the merge has to conflict for the index to hold stages"
    assert _git(worktree, "ls-files", "-u").stdout.strip(), "no unmerged stages were staged"
    shutil.rmtree(worktree)

    reason = _reason_of(_run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    start = reason.index("GIT_INDEX_FILE=")
    end = reason.find(" |", start)
    command = (reason[start:] if end == -1 else reason[start:end]).replace(
        "RECOVERY_DIR", str(tmp_path)
    )
    result = subprocess.run(
        command,
        cwd=git_sandbox.main,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "conflict.txt").exists(), (
        "checkout-index is expected to skip it; the point is that the copy does not"
    )
    stages = subprocess.run(
        ["git", "ls-files", "-s", "-u"],
        cwd=git_sandbox.main,
        env={**os.environ, "GIT_INDEX_FILE": str(tmp_path / "index")},
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
    _git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), "HEAD")
    pointed_at = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    _git(worktree, "update-index", "--add", "--cacheinfo", f"160000,{pointed_at},sub")
    shutil.rmtree(worktree)

    reason = _reason_of(_run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    start = reason.index("GIT_INDEX_FILE=")
    end = reason.find(" |", start)
    command = (reason[start:] if end == -1 else reason[start:end]).replace(
        "RECOVERY_DIR", str(tmp_path)
    )
    result = subprocess.run(
        command,
        cwd=git_sandbox.main,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert list((tmp_path / "sub").iterdir()) == [], (
        "checkout-index is expected to empty it; the point is that the copy is not empty"
    )
    entries = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=git_sandbox.main,
        env={**os.environ, "GIT_INDEX_FILE": str(tmp_path / "index")},
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
    head = _git(git_sandbox.main, "rev-parse", "HEAD").stdout.strip()
    worktree = git_sandbox.root / "healthy-blocked-rescue"
    _git(git_sandbox.main, "worktree", "add", "--detach", str(worktree), head)
    first, second = _abandon_commits(git_sandbox, worktree, 2)

    reason = _reason_of(_run_gc_json(git_sandbox, monkeypatch, capsys), worktree)
    start = reason.index("git branch gc-rescue-")
    end = reason.find(" |", start)
    command = reason[start:] if end == -1 else reason[start:end]
    blocked = command[len("git branch ") :].split()[0]
    survivor = second if blocked.endswith(first) else first
    _git(git_sandbox.main, "branch", blocked, head)

    result = subprocess.run(
        command,
        cwd=git_sandbox.main,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0, "a blocked rescue that exits 0 reads as a completed rescue"
    assert (
        _git(
            git_sandbox.main, "rev-parse", "--verify", f"gc-rescue-{survivor}", check=False
        ).returncode
        != 0
    ), "the chain must stop at the failure rather than carry on past it"
