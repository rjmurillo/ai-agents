"""Shared helpers for the pytest partition coverage tests (issue #6239)."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def selects(args: list[str], rel: str) -> bool:
    """Whether a partition's full argument list would collect ``rel``."""
    ignored = {t.removeprefix("--ignore=") for t in args if t.startswith("--ignore=")}
    globs = [t.removeprefix("--ignore-glob=") for t in args if t.startswith("--ignore-glob=")]
    if rel in ignored or any(fnmatch.fnmatch(rel, g) for g in globs):
        return False
    roots = [t.rstrip("/") for t in args if t.startswith("tests/")]
    return any(rel == root or rel.startswith(f"{root}/") for root in roots)


def tracked_tests() -> list[str]:
    """Git-tracked ``.py`` files under ``tests/``."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", "--", "tests"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [f for f in out.split("\0") if f.endswith(".py")]
