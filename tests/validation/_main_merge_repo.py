"""Real-git builders for a reviewed branch that syncs with main (issue #6509).

The shape under test: a feature branch holds a code commit ``X`` and a review
marker ``M`` on top of it. ``main`` then moves, and the author merges it into
the branch. These helpers build that history in a scratch repository, with an
``origin/main`` ref that follows the local ``main``, so the validators run
against the same ref names production uses.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.validation._review_artifact import commit_marker

BRANCH = "feature"
BASE_REF = "origin/main"


def git(repo: Path, *args: str, check: bool = True) -> str:
    """Run git in ``repo`` with an isolated identity and return stripped stdout.

    ``check=False`` lets a test run a command that is expected to exit non-zero,
    such as a merge that stops on a conflict.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )
    return result.stdout.strip()


def write_commit(repo: Path, name: str, text: str, message: str | None = None) -> str:
    """Write ``name`` with ``text``, commit it, and return the new commit SHA."""
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message or f"edit {name}")
    return git(repo, "rev-parse", "HEAD")


def publish_main(repo: Path) -> None:
    """Point ``origin/main`` at the local ``main``, as a fetch would."""
    git(repo, "update-ref", f"refs/remotes/{BASE_REF}", "main")


def reviewed_branch(repo: Path, axes: str = "analyst,security") -> str:
    """Build main plus a feature branch with a code commit and a marker; return the code SHA.

    Leaves ``feature`` checked out with the marker as HEAD.
    """
    git(repo, "init", "-q", "-b", "main")
    write_commit(repo, "base.txt", "base\n")
    publish_main(repo)
    git(repo, "checkout", "-q", "-b", BRANCH)
    tip = write_commit(repo, "feature.txt", "feature\n")
    commit_marker(repo, axes, tip)
    return tip


def advance_main(repo: Path, name: str = "main.txt", text: str = "main\n") -> str:
    """Land a commit on ``main``, publish it as ``origin/main``, and return to the branch."""
    git(repo, "checkout", "-q", "main")
    sha = write_commit(repo, name, text, message="main moves on")
    publish_main(repo)
    git(repo, "checkout", "-q", BRANCH)
    return sha


def sync_with_main(repo: Path) -> str:
    """Merge ``origin/main`` into the branch and return the merge commit SHA."""
    git(repo, "merge", "-q", "--no-edit", BASE_REF)
    return git(repo, "rev-parse", "HEAD")
