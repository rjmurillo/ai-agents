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


def _base_derived(label: str, module: ModuleType) -> MergeTreeRatchet:
    """Register a base-derived ratchet, reading its script path from the module.

    ``_SCRIPT`` lives in the module that owns it, so a rename edits one place.
    """
    return MergeTreeRatchet(label, None, module, cast(str, module._SCRIPT))


RATCHETS: tuple[MergeTreeRatchet, ...] = (
    _base_derived("ruff count ratchet", ruff_count_ratchet),
    _base_derived("taste count ratchet", taste_count_ratchet),
    _base_derived("type-ignore count ratchet", type_ignore_count_ratchet),
    _base_derived("memory-index count ratchet", memory_index_count_ratchet),
    MergeTreeRatchet(
        "cli exit contract ratchet",
        "scripts/ci/cli_exit_contract_baseline.txt",
        cli_exit_contract_ratchet,
        "scripts/ci/cli_exit_contract_ratchet.py",
    ),
)
