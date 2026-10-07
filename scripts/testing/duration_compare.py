"""Compare one duration snapshot with the median of earlier snapshots.

A module's baseline is the median of its seconds across history snapshots that
ran the same number of tests in it. Change-scoped CI runs execute a subset of
the suite, so a module total is only comparable when the same tests ran. One
consequence: a change that adds a test to a module and also slows it has no
baseline until main records the new count, so that slowdown is not flagged on
the pull request that made it.

The suite baseline is the sum of per-module medians over the comparable
modules, not a median of whole-run totals, because whole runs differ in which
modules they selected.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field

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


def module_baseline(module: str, tests: int, history: Sequence[Snapshot]) -> list[float]:
    """Seconds this module took in each past snapshot that ran the same tests."""
    return [
        s.modules[module]["seconds"]
        for s in history
        if module in s.modules and s.modules[module]["tests"] == tests
    ]


def regressed(seconds: float, baseline: float, ratio: float, min_delta: float) -> bool:
    """Both thresholds must hold, so runner jitter on a fast module does not count."""
    return seconds - baseline >= min_delta and seconds >= baseline * ratio


def compare(current: Snapshot, history: Sequence[Snapshot], limits: Thresholds) -> Comparison:
    """Measure every comparable module, and their sum, against the history median."""
    result = Comparison()
    for module, entry in current.modules.items():
        samples = module_baseline(module, int(entry["tests"]), history)
        if not samples:
            continue
        baseline = statistics.median(samples)
        result.comparable += 1
        result.seconds += entry["seconds"]
        result.baseline += baseline
        result.min_samples = min(result.min_samples or len(samples), len(samples))
        if regressed(entry["seconds"], baseline, limits.module_ratio, limits.module_min_delta):
            result.modules.append(Regression(module, entry["seconds"], baseline, len(samples)))
    result.modules.sort(key=lambda r: (-(r.seconds - r.baseline), r.name))
    if regressed(result.seconds, result.baseline, limits.suite_ratio, limits.suite_min_delta):
        result.suite = Regression("suite", result.seconds, result.baseline, result.min_samples)
    return result
