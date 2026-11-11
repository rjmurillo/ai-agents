"""Shared builders for the publish_wiki tests (issue #7202). No test_ prefix: not collected."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_URL = "https://github.com/acme/widgets"
BLOB = f"{REPO_URL}/blob/main"
TREE = f"{REPO_URL}/tree/main"

README = """# Training

- [First](first-page.md)

- [Second](second-page.md#part)
"""
FIRST = "# First steps\n\nSee [second](./second-page.md#part) and [home](README.md).\n"
SECOND = "# Second steps\n\nRead [the script](../../scripts/tool.py).\n"


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def make_repo(root: Path) -> Path:
    """A repository holding a small docs/training tree and one linkable script."""
    write(root, "docs/training/README.md", README)
    write(root, "docs/training/_template.md", "# Template\n")
    write(root, "docs/training/first-page.md", FIRST)
    write(root, "docs/training/second-page.md", SECOND)
    write(root, "scripts/tool.py", "print('hi')\n")
    (root / "docs" / "assets").mkdir(parents=True)
    return root


def git(args: list[str], cwd: Path) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return done.stdout


ON_WINDOWS = os.name == "nt"


def symlink_or_skip(link: Path, target: Path) -> None:
    """Create ``link`` -> ``target``, or skip when the platform lacks symlink privilege.

    Windows without Developer Mode raises ``OSError``; a platform with no symlink
    support raises ``NotImplementedError``. On POSIX any other ``OSError`` is a
    broken fixture and must fail the test, not skip it.
    """
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except NotImplementedError as exc:
        pytest.skip(f"cannot create symbolic links here: {exc}")
    except OSError as exc:
        if not ON_WINDOWS:
            raise
        pytest.skip(f"cannot create symbolic links here: {exc}")


def make_wiki(tmp_path: Path) -> Path:
    """A bare wiki remote seeded with the hand-made Home page GitHub requires."""
    bare = tmp_path / "wiki.git"
    git(["init", "--bare", "-b", "main", str(bare)], tmp_path)
    seed = tmp_path / "seed"
    git(["clone", str(bare), str(seed)], tmp_path)
    write(seed, "Home.md", "hand made\n")
    write(seed, "Old-Page.md", "stale\n")
    write(seed, "image.png", "binary-ish\n")
    git(["add", "-A"], seed)
    git(["commit", "-m", "seed"], seed)
    git(["push", "origin", "HEAD:main"], seed)
    return bare
