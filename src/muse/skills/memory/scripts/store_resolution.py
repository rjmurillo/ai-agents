"""Repository memory store resolution for search_memory.py (ADR-126).

Each repository has one memory store: `.serena/memories` when that folder
exists, else `.project-toolkit/memory/notes`. This module sits beside
search_memory.py because a shipped script may import only the standard library
or a module beside it (import-closure gate, issue #7221). The router keeps its
own copy in `memory_core/memory_store.py` and the `memory_enhancement` package
keeps a third; the test_memory_root_parity tests hold all three together.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

STORE_DIRS = (Path(".serena", "memories"), Path(".project-toolkit", "memory", "notes"))
_ROOT_MARKER_DIRS = (Path(".serena", "memories"), Path(".project-toolkit", "memory"))
EPISODES_REL = Path(".project-toolkit", "memory", "episodes")


class Stores(NamedTuple):
    """The folders one search reads, plus notes a Serena store shadows."""

    root: Path
    serena: Path | None
    episodes: Path | None
    notes: Path | None
    shadowed_notes: Path | None


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


def _project_root() -> Path:
    # Keep the consumer checkout ahead of the installed plugin directory. With
    # no checkout found, use the current directory, never the plugin's own
    # tree, so a report names the user's project.
    cwd = Path.cwd().resolve()
    return find_memory_root(project_start().resolve()) or find_memory_root(cwd) or cwd


def resolve_stores(
    serena_override: Path | None = None, episodes_override: Path | None = None
) -> Stores:
    """Resolve the one memory store, the episode store, and shadowed notes.

    An explicit override is trusted as given. A default episode store linked
    outside the root is not this project's, so it is not queried. Notes hidden
    by a Serena store are reported, never searched (ADR-126).
    """
    root = _project_root()
    corpora = contained_stores(root)
    serena = serena_override.resolve() if serena_override else corpora.get(STORE_DIRS[0])
    default_episodes = (root / EPISODES_REL).resolve()
    episodes = episodes_override.resolve() if episodes_override else None
    if episodes is None and default_episodes.is_relative_to(root):
        episodes = default_episodes
    notes = corpora.get(STORE_DIRS[1])
    shadowed = None
    if serena is not None and not serena_override and notes and any(notes.rglob("*.md")):
        shadowed = notes
    return Stores(root, serena, episodes, None if serena else notes, shadowed)
