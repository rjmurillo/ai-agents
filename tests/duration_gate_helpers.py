"""Builders for the duration gate tests."""

from __future__ import annotations

from pathlib import Path

from scripts.testing.duration_schema import PartitionEntry
from tests.duration_test_helpers import write_junit


def legs(**seconds: float) -> dict[str, PartitionEntry]:
    """Partitions keyed like JUnit stems: ``split_1`` becomes ``pytest-results-split-1``."""
    return {
        f"pytest-results-{name.replace('_', '-')}": {"tests": 1, "wall_seconds": wall}
        for name, wall in seconds.items()
    }


def write_legs(tmp_path: Path, **walls: float) -> list[str]:
    """One JUnit report per leg, each with ``wall`` seconds of wall time."""
    return [
        str(
            write_junit(
                tmp_path,
                f"pytest-results-{name.replace('_', '-')}",
                {f"tests.test_{name}": [1.0]},
                wall,
            )
        )
        for name, wall in walls.items()
    ]
