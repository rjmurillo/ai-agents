"""How much slower than its baselines a partition's runner was in this run."""

from __future__ import annotations

import statistics

from scripts.testing.duration_snapshot import Snapshot

# A partition needs this many substantial modules before its speed is trusted.
SPEED_MIN_MODULES = 5
SPEED_MIN_BASELINE = 1.0


def partition_speeds(
    current: Snapshot, baselines: dict[str, float]
) -> dict[str, float]:
    """Median seconds-to-baseline ratio of each partition's substantial modules.

    Returns only partitions with ``SPEED_MIN_MODULES`` modules whose baseline is
    at least ``SPEED_MIN_BASELINE`` seconds, floored at 1.0.
    """
    ratios: dict[str, list[float]] = {}
    for module, baseline in baselines.items():
        partition = current.module_partitions.get(module)
        if partition is not None and baseline >= SPEED_MIN_BASELINE:
            ratios.setdefault(partition, []).append(
                current.modules[module]["seconds"] / baseline)
    return {
        partition: max(1.0, statistics.median(values))
        for partition, values in sorted(ratios.items())
        if len(values) >= SPEED_MIN_MODULES
    }
