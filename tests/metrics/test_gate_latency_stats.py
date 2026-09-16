"""Percentile arithmetic for gate_latency (REQ-027 AC-04, AC-05).

Split from ``test_gate_latency.py`` so both stay under the 400-line taste
warning threshold, and because these exercise ``gate_latency_stats``, which
is its own module: pure functions over sample lists, no subprocess and no
clock, so the expectations below are hand-computed rather than observed.
"""

from __future__ import annotations

import pytest

from scripts.metrics import gate_latency_stats as gls

# --- Percentiles (nearest-rank, 1-indexed) -----------------------------------


@pytest.mark.parametrize(
    ("values", "p50", "p95"),
    [
        ([5.0], 5.0, 5.0),
        ([1.0, 2.0], 1.0, 2.0),
        ([1.0, 2.0, 3.0], 2.0, 3.0),
        ([1.0, 2.0, 3.0, 4.0, 5.0], 3.0, 5.0),
        (list(range(1, 21)), 10.0, 19.0),
    ],
)
def test_positive_nearest_rank_percentile_hand_computed(
    values: list[float], p50: float, p95: float
) -> None:
    assert gls._nearest_rank_percentile(values, 50) == p50
    assert gls._nearest_rank_percentile(values, 95) == p95


def test_negative_percentile_of_empty_sample_raises() -> None:
    with pytest.raises(ValueError, match="empty sample"):
        gls._nearest_rank_percentile([], 50)


@pytest.mark.parametrize("n", [1, 2, 3, 5, 19])
def test_positive_percentile_note_present_below_20(n: int) -> None:
    note = gls._percentile_note(n)
    assert note is not None
    assert "upper-order statistic" in note


@pytest.mark.parametrize("n", [20, 21, 100])
def test_negative_percentile_note_absent_at_or_above_20(n: int) -> None:
    assert gls._percentile_note(n) is None


