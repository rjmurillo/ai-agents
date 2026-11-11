"""Shared builders for the publish_wiki tests (issue #7202). No test_ prefix: not collected."""

from __future__ import annotations

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


def symlink_or_skip(link: Path, target: Path) -> None:
    """Create ``link`` -> ``target``, or skip when the platform lacks symlink privilege."""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create symbolic links here: {exc}")
