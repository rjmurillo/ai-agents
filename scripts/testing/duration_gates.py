"""Wall-time gates over a duration snapshot's partitions.

Two checks over the per-leg wall seconds that ``duration_snapshot`` reads from
the JUnit reports:

* a leg that runs longer than ``PARTITION_WALL_LIMIT_SECONDS`` fails the report,
  which leaves headroom before the job timeout kills a leg without a report;
* split legs whose slowest takes more than ``SPLIT_IMBALANCE_RATIO`` times the
  fastest raise a warning, because pytest-split is meant to keep them level.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from scripts.testing.duration_render import escape_command_data
from scripts.testing.duration_schema import PartitionEntry

# The `test` job in .github/workflows/pytest.yml sets timeout-minutes: 10.
# `wall_seconds` is the JUnit testsuite time: pytest's own session time, not the
# job's. Checkout, environment setup, and split-1's primary steps (pins, lint,
# ratchets) add about 95 s measured on PR #6241's run. 480 s leaves 120 s of the
# 600 s limit for that, so a leg over 480 s is one slow run from being killed.
_JOB_TIMEOUT_SECONDS = 10 * 60
PARTITION_WALL_LIMIT_SECONDS = 0.8 * _JOB_TIMEOUT_SECONDS

SPLIT_IMBALANCE_RATIO = 1.5

# Partition keys are JUnit file stems: artifacts/pytest-results-split-1.xml.
_SPLIT_LEG = re.compile(r"^pytest-results-split-\d+$")


@dataclass(frozen=True)
class Imbalance:
    """The slowest and fastest split legs of one run."""

    slowest: str
    slowest_seconds: float
    fastest: str
    fastest_seconds: float

    @property
    def ratio(self) -> float:
        return self.slowest_seconds / self.fastest_seconds


def legs_over_limit(
    partitions: Mapping[str, PartitionEntry], limit: float
) -> list[tuple[str, float]]:
    """Every leg strictly above ``limit`` seconds, slowest first."""
    over = [
        (name, entry["wall_seconds"])
        for name, entry in partitions.items()
        if entry["wall_seconds"] > limit
    ]
    return sorted(over, key=lambda item: (-item[1], item[0]))


def split_imbalance(partitions: Mapping[str, PartitionEntry], ratio: float) -> Imbalance | None:
    """The slowest and fastest split legs when they differ by more than ``ratio``.

    Dedicated legs (safe-push, pr-autofix) run fixed files and are not balanced
    by pytest-split, so they are ignored. A fastest leg with no recorded time
    gives no ratio, so it is skipped rather than divided by.
    """
    walls = {
        name: entry["wall_seconds"] for name, entry in partitions.items() if _SPLIT_LEG.match(name)
    }
    if len(walls) < 2:
        return None
    slowest = max(walls, key=lambda name: (walls[name], name))
    fastest = min(walls, key=lambda name: (walls[name], name))
    if walls[fastest] <= 0:
        return None
    found = Imbalance(slowest, walls[slowest], fastest, walls[fastest])
    return found if found.ratio > ratio else None


def gate_commands(
    over_limit: Sequence[tuple[str, float]], imbalance: Imbalance | None, limit: float
) -> list[str]:
    """Workflow commands for the gates: an error per slow leg, one imbalance warning."""
    lines = [
        "::error title=Test leg wall time::"
        + escape_command_data(f"{name} took {seconds:.1f}s, above the {limit:.0f}s limit")
        for name, seconds in over_limit
    ]
    if imbalance:
        lines.append(
            "::warning title=Split imbalance::"
            + escape_command_data(
                f"{imbalance.slowest} took {imbalance.slowest_seconds:.1f}s and "
                f"{imbalance.fastest} took {imbalance.fastest_seconds:.1f}s "
                f"({imbalance.ratio:.2f}x); split legs should stay level"
            )
        )
    return lines
