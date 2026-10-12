"""Real temporary git repositories for the placement ratchet tests.

No mocks: rename detection and merge-base are git behaviors, so the tests
drive a real repository under ``tmp_path`` with a ``main`` branch.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

MEMORIES = ".serena/memories"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        }
    )
    return env


def git(cwd: Path, *args: str) -> str:
    """Run git in ``cwd`` and return stdout; raise on a non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_env(),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


def make_repo(root: Path) -> Path:
    """Create a repository with one commit on ``main`` and an empty memory tree."""
    git(root, "init", "-q", "-b", "main")
    (root / MEMORIES).mkdir(parents=True)
    (root / "README.md").write_text("# repo\n")
    commit_all(root, "init")
    return root


def write(root: Path, relpath: str, content: str) -> Path:
    """Write ``content`` to ``relpath`` under ``root``, creating parents."""
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def commit_all(root: Path, message: str) -> None:
    """Stage everything and commit."""
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
