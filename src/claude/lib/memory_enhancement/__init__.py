"""Memory Enhancement Layer for AI Agents.

Provides citation tracking, verification, graph traversal,
health reporting, and confidence scoring for the memory system.
"""

from __future__ import annotations

from pathlib import Path

__version__ = "0.3.0"


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from start directory looking for .git to find repo root."""
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None
