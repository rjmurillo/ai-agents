"""Shared fixtures for the citation-freshness gate tests (issue #5337).

Fixture citations are composed with f-strings over ``TARGET``/``GONE`` so
these files' own added lines never present a repo-relative citation to the
gate when it scans the branch that introduces them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_citation_freshness as checker

TARGET = "lib/util.py"
GONE = "lib/missing.py"

TARGET_CONTENT = "\n".join(
    [
        "# helper module",
        "PLACEHOLDER = 0",
        "def magic_token():",
        "    return 1",
        "TAIL = 2",
    ]
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _repo(tmp_path: Path) -> Path:
    """Create a repo whose main branch tracks the cited target file."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    target = root / TARGET
    target.parent.mkdir(parents=True)
    target.write_text(TARGET_CONTENT + "\n", encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


def _add_doc(root: Path, relpath: str, text: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "docs")


def _run(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = checker.main(["--repo-root", str(root), "--base", "main"])
    return code, capsys.readouterr().out


