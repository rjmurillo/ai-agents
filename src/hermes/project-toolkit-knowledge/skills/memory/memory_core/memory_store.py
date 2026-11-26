"""Repository memory store resolution for the shipped memory skill (ADR-126).

Each repository has one memory store: `.serena/memories` when that folder
exists, else `.project-toolkit/memory/notes`. This module is stdlib-only so the
router and `scripts/store_resolution.py` can share it in a plugin install. The
`memory_enhancement` package keeps its own copy for repo hooks; the
test_memory_root_parity tests hold both together.
"""

from __future__ import annotations

import os
from pathlib import Path

STORE_DIRS = (Path(".serena", "memories"), Path(".project-toolkit", "memory", "notes"))
_ROOT_MARKER_DIRS = (Path(".serena", "memories"), Path(".project-toolkit", "memory"))


def find_memory_root(start: Path) -> Path | None:
    """Return the nearest ancestor holding `.git` or a memory folder."""
    for parent in (start, *start.parents):
        if (parent / ".git").exists() or any((parent / m).is_dir() for m in _ROOT_MARKER_DIRS):
            return parent
    return None


def contained_stores(root: Path) -> dict[Path, Path]:
    """Map each store folder that exists inside `root` to its resolved path.

    A folder that resolves outside `root`, or to `root` itself, is dropped.
    """
    stores: dict[Path, Path] = {}
    for relative in STORE_DIRS:
        candidate = root / relative
        if candidate.is_dir():
            resolved = candidate.resolve()
            if resolved != root and resolved.is_relative_to(root):
                stores[relative] = resolved
    return stores


def project_start() -> Path:
    """Start from the host's project directory, else the current directory."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(project_dir) if project_dir else Path.cwd()


def resolve_memory_store(start: Path | None = None) -> Path | None:
    """Return the repository's one memory store, or None when it has none."""
    root = find_memory_root((start or project_start()).resolve())
    if root is None:
        return None
    return next(iter(contained_stores(root).values()), None)
