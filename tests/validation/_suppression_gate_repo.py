"""Throwaway git repos and the three suppression-gate entry points.

The staged, push, and CI diff checks must give the same verdict. Tests run
one change through all three with ``ENTRY_POINTS``.
"""

from __future__ import annotations

import io
import subprocess
from collections.abc import Callable
from pathlib import Path

from scripts.validation import git_hook_policy as policy


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return its stripped stdout."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    ).stdout.strip()


def init_repo(tmp_path: Path) -> Path:
    """Create an empty repo that stores every byte as written."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "core.autocrlf", "false")
    # A global attributes file can still normalize line endings on add.
    (repo / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (repo / ".git" / "info" / "attributes").write_text("* -text\n", encoding="utf-8")
    return repo


def write(repo: Path, path: str, body: str) -> None:
    """Write ``body`` to ``path`` inside ``repo``, creating parents."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def _staged(repo: Path, _base: str) -> int:
    return policy.check_staged_suppressions(repo)


def _pushed(repo: Path, base: str) -> int:
    git(repo, "commit", "-q", "-m", "head")
    head = git(repo, "rev-parse", "HEAD")
    stream = io.StringIO(f"refs/heads/feature {head} refs/heads/feature {base}\n")
    return policy.check_pushed_suppressions(stream, repo)


def _ci_diff(repo: Path, base: str) -> int:
    git(repo, "commit", "-q", "-m", "head")
    return policy.check_suppression_diff(base, repo)


ENTRY_POINTS: list[Callable[[Path, str], int]] = [_staged, _pushed, _ci_diff]
ENTRY_IDS = ["staged", "push", "ci-diff"]
