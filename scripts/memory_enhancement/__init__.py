"""Memory Enhancement Layer for AI Agents.

Provides citation tracking, verification, graph traversal,
health reporting, and confidence scoring for the memory system.
"""

from __future__ import annotations

from pathlib import Path

__version__ = "0.3.0"


# Repository memory stores, in preference order. The search_memory.py skill
# script ships stdlib-only and keeps its own copy of these paths; a parity
# test holds the two root rules together.
MEMORY_STORE_DIRS = (
    Path(".serena", "memories"),
    Path(".project-toolkit", "memory", "notes"),
)
_TOOLKIT_MEMORY_DIR = Path(".project-toolkit", "memory")


def find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from start directory looking for .git to find repo root."""
    current = start or Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def find_memory_root(start: Path | None = None) -> Path | None:
    """Return the nearest ancestor that is a checkout or holds a memory store.

    A project with no ``.git`` (an unpacked archive) still has a root when it
    carries a memory store, and the nearest marker wins over an outer checkout.
    """
    current = (start or Path.cwd()).resolve()
    for parent in (current, *current.parents):
        if (
            (parent / ".git").exists()
            or (parent / MEMORY_STORE_DIRS[0]).is_dir()
            or (parent / _TOOLKIT_MEMORY_DIR).is_dir()
        ):
            return parent
    return None


def repository_memory_dir(repo_root: Path) -> Path | None:
    """Use the established project corpus or the default repository notes."""
    root = repo_root.resolve()
    for relative in MEMORY_STORE_DIRS:
        candidate = root / relative
        if candidate.is_dir():
            resolved = candidate.resolve()
            if resolved != root and resolved.is_relative_to(root):
                return resolved
    return None
