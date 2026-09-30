"""Single ownership registry for ratchets evaluated on a synthetic merge tree."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import cast

from scripts.ci import (
    cli_exit_contract_ratchet,
    memory_index_count_ratchet,
    ruff_count_ratchet,
    taste_count_ratchet,
    type_ignore_count_ratchet,
)


@dataclass(frozen=True, slots=True)
class MergeTreeRatchet:
    """One ratchet the merge-tree gate evaluates.

    ``baseline_path`` names a committed scalar. It is None for a base-derived
    ratchet (issue #5363), whose ceiling is the count measured on the base tip
    rather than a stored number; ``script_path`` then marks the bootstrap state
    where the base tip does not carry the ratchet yet.
    """

    label: str
    baseline_path: str | None
    counter_module: ModuleType
    script_path: str

    def current_count(self, repo_root: Path) -> int | None:
        counter = cast(
            Callable[[Path], int | None],
            self.counter_module.current_count,
        )
        return counter(repo_root)


RATCHETS: tuple[MergeTreeRatchet, ...] = (
    MergeTreeRatchet(
        "ruff count ratchet",
        None,
        ruff_count_ratchet,
        "scripts/ci/ruff_count_ratchet.py",
    ),
    MergeTreeRatchet(
        "taste count ratchet",
        None,
        taste_count_ratchet,
        "scripts/ci/taste_count_ratchet.py",
    ),
    MergeTreeRatchet(
        "type-ignore count ratchet",
        None,
        type_ignore_count_ratchet,
        "scripts/ci/type_ignore_count_ratchet.py",
    ),
    MergeTreeRatchet(
        "memory-index count ratchet",
        None,
        memory_index_count_ratchet,
        "scripts/ci/memory_index_count_ratchet.py",
    ),
    MergeTreeRatchet(
        "cli exit contract ratchet",
        "scripts/ci/cli_exit_contract_baseline.txt",
        cli_exit_contract_ratchet,
        "scripts/ci/cli_exit_contract_ratchet.py",
    ),
)
