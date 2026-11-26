"""Repository memory store resolution (ADR-126).

Each repository has one memory store: ``.serena/memories`` when that folder
exists, else ``.project-toolkit/memory/notes``. This package ships only in the
Claude plugin lib, and the memory skill ships to five more trees, so the skill
keeps one copy in ``memory_core/memory_store.py`` (imported by
``scripts/store_resolution.py`` for the search script). The
test_memory_root_parity tests hold both copies together.
"""

from __future__ import annotations

from pathlib import Path

# Repository memory stores, in preference order.
MEMORY_STORE_DIRS = (
    Path(".serena", "memories"),
    Path(".project-toolkit", "memory", "notes"),
)
_TOOLKIT_MEMORY_DIR = Path(".project-toolkit", "memory")


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


def shadowed_notes_dir(repo_root: Path) -> Path | None:
    """Return the notes folder when it holds memories the Serena store hides.

    ADR-126 reads one store. Once ``.serena/memories`` exists, notes written
    earlier are no longer searched, so callers report them instead.
    """
    root = repo_root.resolve()
    store = repository_memory_dir(root)
    notes = root / MEMORY_STORE_DIRS[1]
    if store is None or not notes.is_dir():
        return None
    resolved = notes.resolve()
    if resolved == store or not resolved.is_relative_to(root):
        return None
    return resolved if any(resolved.rglob("*.md")) else None
