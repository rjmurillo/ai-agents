"""Compare one duration snapshot with the median of earlier snapshots.

A partition runs on one runner, and runner speed is bimodal: the same tests
take 1.5x to 1.6x longer on a slow runner, on main pushes and pull requests
alike. A module is therefore measured against its baseline scaled by how much
slower its partition's other modules ran, so only a module slower than its own
partition is a regression. A partition never scales the baseline below 1.0, and never above
``SPEED_CAP``: a partition slower than the cap is itself a regression. The
suite-level check scales each module's baseline by the same capped partition
speed, so the sum of scaled baselines is the suite baseline.

A module's baseline is the median of its seconds across history snapshots that
ran exactly the same tests in it, matched by a digest of the test IDs.
Change-scoped CI runs execute a subset of the suite, and a pull request can
replace a test with another, so a module total is only comparable when the
same tests ran. One consequence: a change that adds, removes, or renames a test
in a module has no baseline for that module until main records the new set, so
a slowdown in that module is not flagged on the pull request that made it.

The suite baseline is the sum of per-module medians over the comparable
modules, not a median of whole-run totals, because whole runs differ in which
modules they selected.

A module is flagged against the larger of its scaled median and the upper
quartile of its samples. Some modules' seconds on main are bimodal:
``tests/validation/test_baseline_integrity.py`` ran 22.9s to 25.7s on 21 of
the 29 main runs that recorded it, 12.8s to 17.5s on 7, and 19.4s on one
(issue #6244). When the fast runs fill the window the median drops toward the
fast mode, and an ordinary run on the slow mode then reads as 1.5x. The upper
quartile sits on the slow mode while fewer than three quarters of the samples
are fast. Replayed over the 30 main snapshots recorded 2026-10-08 to 2026-10-11
(the first three served only as history, so 27 runs were judged), the median
rule raised 8 module flags on 6 runs and the upper-quartile rule raised 5 on 5,
both without partition scaling. The three it dropped sit inside the range main
recorded on later runs. The five flags it kept come from the two slowdowns that
PR #6261 and PR #6267 went on to fix: one module on four runs, one on one.

``Regression.baseline`` and the rendered ratio still report the median, so a
flagged module can read as further over its baseline than the quartile it was
judged against.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from scripts.testing.duration_partition_speed import SPEED_CAP, partition_speeds, scaled_baselines
from scripts.testing.duration_snapshot import Snapshot


@dataclass
class Regression:
    """A module, or the suite, slower than its baseline beyond both thresholds."""

    name: str
    seconds: float
    baseline: float
    samples: int


@dataclass
class Thresholds:
    module_ratio: float
    module_min_delta: float
    suite_ratio: float
    suite_min_delta: float


@dataclass
class Comparison:
    """This snapshot measured against the history baseline.

    ``min_samples`` is the fewest history samples behind any comparable
    module, so the suite verdict never claims more evidence than its weakest
    module had.
    """

    comparable: int = 0
    seconds: float = 0.0
    baseline: float = 0.0
    min_samples: int = 0
    modules: list[Regression] = field(default_factory=list)
    suite: Regression | None = None
    speeds: dict[str, float] = field(default_factory=dict)


def module_baseline(module: str, ids: str, history: list[Snapshot]) -> list[float]:
    """Seconds this module took in each past snapshot that ran the same tests."""
    return [
        s.modules[module]["seconds"]
        for s in history
        if module in s.modules and s.modules[module]["ids"] == ids
    ]


def upper_quartile(samples: list[float]) -> float:
    """The 75th percentile of ``samples``, interpolated; one sample is its own quartile."""
    if len(samples) == 1:
        return samples[0]
    return statistics.quantiles(samples, n=4, method="inclusive")[2]


def regressed(seconds: float, baseline: float, ratio: float, min_delta: float) -> bool:
    """Both thresholds must hold, so runner jitter on a fast module does not count."""
    return seconds - baseline >= min_delta and seconds >= baseline * ratio


def _slow_partitions(
    current: Snapshot,
    baselines: dict[str, float],
    samples: dict[str, int],
    speeds: dict[str, float],
) -> list[Regression]:
    """One regression per partition slower than ``SPEED_CAP``, summed over its modules."""
    found = []
    for partition, speed in speeds.items():
        if speed <= SPEED_CAP:
            continue
        members = [m for m in baselines if current.module_partitions.get(m) == partition]
        found.append(
            Regression(
                f"partition {partition}",
                sum(current.modules[m]["seconds"] for m in members),
                sum(baselines[m] for m in members),
                min(samples[m] for m in members),
            )
        )
    return found


def compare(current: Snapshot, history: list[Snapshot], limits: Thresholds) -> Comparison:
    """Measure every comparable module against the larger of its scaled median and
    upper quartile, and their sum against the summed medians."""
    result = Comparison()
    baselines: dict[str, float] = {}
    quartiles: dict[str, float] = {}
    sample_counts: dict[str, int] = {}
    for module, entry in current.modules.items():
        samples = module_baseline(module, entry["ids"], history)
        if not samples:
            continue
        baselines[module] = statistics.median(samples)
        quartiles[module] = upper_quartile(samples)
        sample_counts[module] = len(samples)
        result.comparable += 1
        result.seconds += entry["seconds"]
        result.baseline += baselines[module]
        result.min_samples = min(result.min_samples or len(samples), len(samples))
    result.speeds = partition_speeds(current, baselines)
    scaled = scaled_baselines(current, baselines, result.speeds)
    for module, baseline in baselines.items():
        seconds = current.modules[module]["seconds"]
        reference = max(scaled[module], quartiles[module])
        if regressed(seconds, reference, limits.module_ratio, limits.module_min_delta):
            result.modules.append(Regression(module, seconds, baseline, sample_counts[module]))
    result.modules += _slow_partitions(current, baselines, sample_counts, result.speeds)
    result.modules.sort(key=lambda r: (-(r.seconds - r.baseline), r.name))
    if regressed(result.seconds, sum(scaled.values()), limits.suite_ratio, limits.suite_min_delta):
        result.suite = Regression("suite", result.seconds, result.baseline, result.min_samples)
    return result
