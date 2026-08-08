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
    label: str
    baseline_path: str
    counter_module: ModuleType
    trigger_globs: tuple[str, ...]

    def current_count(self, repo_root: Path) -> int | None:
        counter = cast(
            Callable[[Path], int | None],
            self.counter_module.current_count,
        )
        return counter(repo_root)


_PYTHON = ("**/*.py",)

RATCHETS: tuple[MergeTreeRatchet, ...] = (
    MergeTreeRatchet(
        "ruff count ratchet",
        "scripts/ci/ruff_count_baseline.txt",
        ruff_count_ratchet,
        _PYTHON,
    ),
    MergeTreeRatchet(
        "taste count ratchet",
        "scripts/ci/taste_count_baseline.txt",
        taste_count_ratchet,
        (
            "**/*.bash",
            "**/*.json",
            "**/*.md",
            "**/*.ps1",
            "**/*.psm1",
            "**/*.sh",
            "**/*.yaml",
            "**/*.yml",
        ),
    ),
    MergeTreeRatchet(
        "type-ignore count ratchet",
        "scripts/ci/type_ignore_count_baseline.txt",
        type_ignore_count_ratchet,
        _PYTHON,
    ),
    MergeTreeRatchet(
        "memory-index count ratchet",
        "scripts/ci/memory_index_count_baseline.txt",
        memory_index_count_ratchet,
        (".serena/memories/**/*.md",),
    ),
    MergeTreeRatchet(
        "cli exit contract ratchet",
        "scripts/ci/cli_exit_contract_baseline.txt",
        cli_exit_contract_ratchet,
        _PYTHON,
    ),
)


def trigger_globs() -> frozenset[str]:
    """Return the exact lefthook trigger union for every registered ratchet."""
    globs = {ratchet.baseline_path for ratchet in RATCHETS}
    for ratchet in RATCHETS:
        globs.update(ratchet.trigger_globs)
    return frozenset(globs)
