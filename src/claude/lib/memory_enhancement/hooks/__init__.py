"""Claude Code hooks for memory-aware prompt enrichment."""

from __future__ import annotations

from ..stores import find_memory_root, repository_memory_dir

__all__ = ["find_memory_root", "repository_memory_dir"]
