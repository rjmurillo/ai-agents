"""How much slower than its baselines a partition's runner was in this run."""

from __future__ import annotations

import statistics

from scripts.testing.duration_snapshot import Snapshot

# A partition needs this many substantial modules before its speed is trusted.
SPEED_MIN_MODULES = 5
SPEED_MIN_BASELINE = 1.0
# Runner variance measured on ubuntu-latest: the same 20755 split-3 tests ran
# 1.56x slower on a slow runner (run 38089251846 against 38089292761, a median
# per-module ratio of 1.56). A partition slower than this is not runner noise,
# so its speed is never used to scale baselines past the cap, and the partition
# itself is reported as a regression.
SPEED_CAP = 1.6


def partition_speeds(
    current: Snapshot, baselines: dict[str, float]
) -> dict[str, float]:
    """Median seconds-to-baseline ratio of each partition's substantial modules.

    Returns only partitions with ``SPEED_MIN_MODULES`` modules whose baseline is
    at least ``SPEED_MIN_BASELINE`` seconds, floored at 1.0. The speed
    is not capped; callers cap it with ``SPEED_CAP`` before scaling.
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
