"""Tests for scripts/eval/_eval_common.py::percentile (REQ-042 AC-11).

Behavior under test: the single merged percentile helper that replaces the
two formerly-private ``_percentile`` copies in ``_model_sweep_core.py`` and
``_report_aggregator.py``. Pure function, so no mocking is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "eval"))

from _eval_common import percentile


def test_percentile_empty_sequence_is_zero() -> None:
    assert percentile([], 50.0) == 0.0


def test_percentile_single_value_ignores_percentile_argument() -> None:
    assert percentile([7.0], 0.0) == 7.0
    assert percentile([7.0], 100.0) == 7.0


def test_percentile_p0_is_the_minimum() -> None:
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.0) == 1.0


def test_percentile_p100_is_the_maximum() -> None:
    assert percentile([4.0, 1.0, 3.0, 2.0], 100.0) == 4.0


def test_percentile_interpolates_between_ranks() -> None:
    # sorted: [1, 2, 3, 4]; rank at p50 = 0.5 * 3 = 1.5 -> interpolate 2 and 3.
    assert percentile([1.0, 2.0, 3.0, 4.0], 50.0) == 2.5


def test_percentile_does_not_require_pre_sorted_input() -> None:
    assert percentile([3.0, 1.0, 2.0], 50.0) == percentile([1.0, 2.0, 3.0], 50.0)
