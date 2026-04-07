"""Claude Code hooks for memory-aware prompt enrichment."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from start directory looking for .git to find repo root."""
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None
