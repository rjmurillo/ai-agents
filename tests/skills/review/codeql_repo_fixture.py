"""Real git repositories for the /review CodeQL pre-step tests.

pytest-zero-collection: helper module, not a suite.

The guard's job is to read a diff from git, so the tests use real repositories
(a bare ``origin`` plus a clone) instead of stubbing git output. Config is
isolated so the developer's global git config cannot change the result.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def write(root: Path, relative: str, text: str = "x\n") -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def make_repo(tmp_path: Path) -> Path:
    """Return a clone on branch ``feature`` that is one commit past ``origin/main``."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    git(tmp_path, "clone", str(origin), str(work))
    git(work, "checkout", "-b", "main")
    write(work, "README.md")
    write(work, ".codeql/scripts/old.py")
    write(work, "src/app.py", "print(1)\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "base")
    git(work, "push", "origin", "main")
    git(work, "remote", "set-head", "origin", "main")
    # The CLI, the database cache, and SARIF output are build artifacts, not tracked files.
    exclude = work / ".git" / "info" / "exclude"
    exclude.write_text(".codeql/cli/\n.codeql/db/\n.codeql/results/\n", encoding="utf-8")
    git(work, "checkout", "-b", "feature")
    write(work, "src/new.py")
    git(work, "add", "-A")
    git(work, "commit", "-m", "feature")
    return work
