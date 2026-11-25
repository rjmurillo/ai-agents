"""Accuracy, percentile, and detectable-gap arithmetic for the actionability eval.

Split out of ``actionability_score.py``, which re-exports every name here. Pure functions over
numbers: nothing here reads a corpus or a predictions file.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

# Two-sided alpha 0.05 and 80 percent power: z(0.975) + z(0.80).
Z_ALPHA_PLUS_Z_BETA = 1.96 + 0.8416


def metrics(predicted: Sequence[bool], truth: Sequence[bool]) -> dict[str, Any]:
    """Accuracy, precision, and recall with actionable as the positive class.

    A zero denominator gives None, not 0.
    """
    if len(predicted) != len(truth):
        raise ValueError(f"length mismatch: {len(predicted)} predicted, {len(truth)} truth")
    n = len(truth)
    pairs = list(zip(predicted, truth, strict=True))
    true_pos = sum(1 for p, t in pairs if p and t)
    false_pos = sum(1 for p, t in pairs if p and not t)
    false_neg = sum(1 for p, t in pairs if not p and t)
    correct = sum(1 for p, t in pairs if p == t)
    return {
        "n": n,
        "accuracy": correct / n if n else None,
        "precision": true_pos / (true_pos + false_pos) if true_pos + false_pos else None,
        "recall": true_pos / (true_pos + false_neg) if true_pos + false_neg else None,
    }


def _rank_value(ordered: Sequence[float], percentile: float) -> float:
    """Value at nearest rank ceil(p/100 * n) of a non-empty, sorted sequence."""
    rank = math.ceil(round(percentile * len(ordered) / 100, 9))
    return ordered[min(len(ordered), max(1, rank)) - 1]


def nearest_rank(values: Sequence[float], percentile: float) -> float | None:
    """Nearest-rank percentile: the value at rank ceil(p/100 * n). None when empty."""
    return _rank_value(sorted(values), percentile) if values else None


def min_detectable_gap(n: int, discordance: float) -> float | None:
    """Smallest accuracy gap a paired test of ``n`` rows detects at 80 percent power.

    This is approximate (normal approximation): it treats rows as independent, which the
    PR-clustered bootstrap does not. ``discordance`` is the share of rows where the two arms
    differ in correctness.
    """
    if n <= 0:
        return None
    return Z_ALPHA_PLUS_Z_BETA * math.sqrt(discordance / n)


def gap_from_counts(correct_c: int, correct_best: int, n: int) -> float:
    """Accuracy gap from integer counts, so a 6-in-60 gap equals 0.1 with no float drift."""
    if n <= 0:
        raise ValueError("n must be positive")
    return (correct_c - correct_best) / n
