"""Shared fixtures for the measurement-anchoring gate tests (issue #5771).

Fixture claims are composed from the pieces below so these files' own lines
never read as a tree-state count to any text scan of this tree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_measurement_anchoring as checker

UNANCHORED = "This tree holds 47 tracked files."
ANCHORED = "This tree holds 47 tracked files (measured at 55ec6212c)."
DATED = "This tree holds 47 tracked files (measured 2026-09-15)."
THRESHOLD = "Methods stay under 60 lines."


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )


def _repo(tmp_path: Path) -> Path:
    """Create a repo on a feature branch cut from a one-file main."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
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


def _run(root: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str]:
    code = checker.main(["--repo-root", str(root), "--base", "main", *extra])
    return code, capsys.readouterr().out


def cite(path: str, line: int) -> str:
    """Return the ``path:line:`` prefix a finding carries.

    Built at runtime so this tree's test sources never hold a literal
    ``path:line`` shape for the citation-freshness gate to resolve.
    """
    return f"{path}:{line}:"
