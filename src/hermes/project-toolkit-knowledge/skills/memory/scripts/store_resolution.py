"""Repository memory store resolution for search_memory.py (ADR-126).

Each repository has one memory store: `.serena/memories` when that folder
exists, else `.project-toolkit/memory/notes`. This module sits beside
search_memory.py and imports the shared store rule from
`memory_core.memory_store` via the skill-root `sys.path` bootstrap accepted
by the import-closure gate (issue #7221). The `memory_enhancement` package
keeps its own copy for repo hooks; the test_memory_root_parity tests hold both
together.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory_core.memory_store import (
    STORE_DIRS,
    contained_stores,
    find_memory_root,
    project_start,
)

EPISODES_REL = Path(".project-toolkit", "memory", "episodes")


class Stores(NamedTuple):
    """The folders one search reads, plus notes a Serena store shadows."""

    root: Path
    serena: Path | None
    episodes: Path | None
    notes: Path | None
    shadowed_notes: Path | None


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
