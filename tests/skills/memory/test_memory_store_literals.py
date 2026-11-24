"""serena_integration.py spells each store path as a literal; pin it to the source.

The symlink scope check in ``load_memory`` names the two store folders as
string literals so that module imports nothing new. A literal that drifts from
``MEMORY_STORE_DIRS`` would shrink the scope to the store itself, and a linked
memory elsewhere in the repository would stop loading.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_enhancement.serena_integration import load_memory
from memory_enhancement.stores import MEMORY_STORE_DIRS


def _linked_memory(tmp_path: Path, store: Path, target_dir: Path) -> Path:
    corpus = tmp_path / "repo" / store
    corpus.mkdir(parents=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "linked.md"
    target.write_text("# Linked\n\nBody.\n", encoding="utf-8")
    link = corpus / "linked.md"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    return corpus


@pytest.mark.parametrize("store", MEMORY_STORE_DIRS, ids=str)
def test_link_inside_the_repository_loads(tmp_path: Path, store: Path) -> None:
    corpus = _linked_memory(tmp_path, store, tmp_path / "repo" / "docs")

    assert load_memory(corpus / "linked.md", corpus) is not None


@pytest.mark.parametrize("store", MEMORY_STORE_DIRS, ids=str)
def test_link_outside_the_repository_is_refused(tmp_path: Path, store: Path) -> None:
    corpus = _linked_memory(tmp_path, store, tmp_path / "elsewhere")

    assert load_memory(corpus / "linked.md", corpus) is None
