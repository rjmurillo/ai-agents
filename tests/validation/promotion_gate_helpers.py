"""Shared git fixtures for the promotion gate tests.

A real temporary repository, because the checks under test read git state and a
stub would only restate the implementation.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` with a fixed identity and return stripped stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
             "PATH": os.environ["PATH"], "HOME": str(repo)},
    )  # fmt: skip
    return result.stdout.strip()


def make_clone(tmp_path: Path) -> tuple[Path, str, str]:
    """A repo with main at ``first``, a side commit ``side``, and tag v1 on ``first``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "a").write_text("1", encoding="utf-8")
    git(repo, "add", "a")
    git(repo, "commit", "-q", "-m", "one")
    first = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "side")
    (repo / "b").write_text("2", encoding="utf-8")
    git(repo, "add", "b")
    git(repo, "commit", "-q", "-m", "side")
    side = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    git(repo, "tag", "v1", first)
    return repo, first, side
