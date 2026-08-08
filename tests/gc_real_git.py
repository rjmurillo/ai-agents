"""A disposable real repository, shared by the worktree GC suites that need one.

Four suites build the same thing: a bare origin, a clone with one commit
pushed to it, and linked worktrees added on top. Each carried its own copy,
so a fix to one, the ``check`` keyword that lets a test assert a git command
fails, reached only the suite it was written in.

The sandbox is real because the questions are about git. Whether
``for-each-ref --contains`` finds a commit, whether git marks a locked entry
prunable, whether ``rev-list --not --all`` looks at other worktrees' HEADs,
and whether a printed recovery command recovers anything are facts about git,
and a mock of git answers whatever it was told to.

Temporary directories live under ``.pytest_tmp`` inside the repository rather
than the system temp dir. Some of these tests register worktrees, and git
records absolute paths, so keeping them on the same filesystem as the checkout
avoids the cross-device cases that have nothing to do with what is under test.
"""

from __future__ import annotations

import json
import shlex
import subprocess
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


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run git in ``cwd``. ``check=False`` is for asserting a command fails."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def write_and_commit(cwd: Path, relative_path: str, content: str, message: str) -> str:
    """Commit ``content`` at ``relative_path`` and return the new commit."""
    path = cwd / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(cwd, "add", relative_path)
    git(cwd, "commit", "-m", message)
    return git(cwd, "rev-parse", "HEAD").stdout.strip()


def run_gc_json(
    sandbox: GitSandbox,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    """Run the tool as the CLI does and return the report it printed."""
    monkeypatch.chdir(sandbox.main)
    code = gc_worktrees.main(["--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.err == "", "a --json run that writes to stderr is not machine-readable"
    return json.loads(captured.out)


def decision_for(report: dict[str, object], path: Path) -> dict[str, object]:
    """The one decision naming ``path``, or an assertion failure."""
    decisions = report["decisions"]
    assert isinstance(decisions, list)
    matches = [d for d in decisions if isinstance(d, dict) and d["path"] == str(path)]
    assert len(matches) == 1, f"expected exactly one decision for {path}, got {len(matches)}"
    return matches[0]


def reason_of(report: dict[str, object], path: Path) -> str:
    """The reason text for ``path``."""
    reason = decision_for(report, path)["reason"]
    assert isinstance(reason, str)
    return reason


def command_of(reason: str, start_marker: str, recovery_dir: Path | None = None) -> str:
    """The runnable chain a reader would paste, sliced out of ``reason``.

    The reason text mixes a runnable command with prose, delimited by ``" | "``.
    A reader copies from the start of the chain to that delimiter, so the tests
    have to slice the same way or they prove nothing about what the reader runs.
    ``recovery_dir`` substitutes every ``RECOVERY_DIR`` placeholder; pass a path
    that does not exist yet, because creating it is the command's job.
    """
    start = reason.index(start_marker)
    end = reason.find(" |", start)
    command = reason[start:] if end == -1 else reason[start:end]
    if recovery_dir is None:
        return command
    assert not recovery_dir.exists(), (
        "substituting a directory that already exists hides whether the command creates it"
    )
    return command.replace("RECOVERY_DIR", shlex.quote(str(recovery_dir)))
