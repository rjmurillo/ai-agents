"""Claude Code hooks for memory-aware prompt enrichment."""

from __future__ import annotations

from pathlib import Path

from .. import find_repo_root

__all__ = ["find_repo_root", "repository_memory_dir"]


def repository_memory_dir(repo_root: Path) -> Path | None:
    """Use the established project corpus or the default repository notes."""
    root = repo_root.resolve()
    for relative in (".serena/memories", ".project-toolkit/memory/notes"):
        candidate = root / relative
        if candidate.is_dir():
            resolved = candidate.resolve()
            if resolved != root and resolved.is_relative_to(root):
                return resolved
    return None
