"""The bootstrap compares arm C with the better of A and B inside every draw (review finding 2).

When the A-versus-B ranking flips between PR resamples, a baseline fixed from the full sample
is too easy in the draws where the other arm leads. The interval then reads tighter than the
data support and can pass a fallback that does not clear the bar against the best baseline.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import make_prediction, make_row, sc

_ROWS = 60
_EXTRA_WINS = 10
_SEED = 7
_ITERATIONS = 2000


def _flipping_baselines() -> tuple[list[int], list[int], list[int]]:
    """A is right on a random half, B on the other half, C is A plus 10 rows A got wrong."""
    rng = random.Random(0)
    a = [1] * (_ROWS // 2) + [0] * (_ROWS // 2)
    rng.shuffle(a)
    b = [1 - flag for flag in a]
    c = list(a)
    wrong = [i for i, flag in enumerate(a) if not flag]
    for i in rng.sample(wrong, _EXTRA_WINS):
        c[i] = 1
    return a, b, c


def _report(a: list[int], b: list[int], c: list[int]) -> dict[str, Any]:
    """Score fake arms that are right on the rows each flag list marks with 1.

    Every row is labeled actionable, so an arm is right exactly when it answers True.
    """
    ids = [f"H{i}" for i in range(len(a))]
    rows = [make_row(row_id, label="actionable") for row_id in ids]
    flags = {row_id: (a[i], b[i], c[i]) for i, row_id in enumerate(ids)}

    def arm(index: int) -> Any:
        return lambda row, record: bool(flags[row["id"]][index])

    arms = {"A": arm(0), "B": arm(1), "C": arm(2)}
    predictions = [make_prediction(row_id) for row_id in ids]
    return sc.build_report(rows, predictions, arms, seed=_SEED, iterations=_ITERATIONS)


class TestBestBaselinePerDraw:
    def test_flipping_baselines_stop_a_fixed_baseline_pass(self) -> None:
        """Against fixed A the interval is (0.067, 0.283) and passes. Against the draw's best it
        reaches below zero, so the verdict is inconclusive."""
        a, b, c = _flipping_baselines()
        fixed_diffs = [ci - ai for ci, ai in zip(c, a, strict=True)]
        fixed_low, _ = sc.paired_bootstrap_ci(
            fixed_diffs, _SEED, _ITERATIONS, clusters=list(range(_ROWS))
        )

        report = _report(a, b, c)

        assert fixed_low > 0
        assert report["gap"] == pytest.approx(_EXTRA_WINS / _ROWS)
        assert report["gap_ci"][0] < 0
        assert report["verdict"] == "inconclusive"

    def test_a_clearly_worse_b_leaves_the_interval_unchanged(self) -> None:
        """No over-fire: when A beats B in every draw, best-per-draw equals fixed A."""
        a, _, c = _flipping_baselines()
        b = [0] * _ROWS
        fixed_diffs = [ci - ai for ci, ai in zip(c, a, strict=True)]
        expected = sc.paired_bootstrap_ci(
            fixed_diffs, _SEED, _ITERATIONS, clusters=list(range(_ROWS))
        )

        report = _report(a, b, c)

        assert tuple(report["gap_ci"]) == expected
        assert report["best_baseline"] == "A"

    def test_a_tie_reports_a_as_the_baseline_and_keeps_the_point_gap(self) -> None:
        """A wins ties for the point estimate, as before."""
        a, b, c = _flipping_baselines()

        report = _report(a, b, c)

        assert sum(a) == sum(b)
        assert report["best_baseline"] == "A"

    def test_every_draw_takes_the_higher_baseline(self) -> None:
        """Two PRs: A wins one, B wins the other. Drawing one PR twice gives the leading arm a full
        score, so C gains nothing. Drawing both ties them at 1 of 2, so the gap is 0.5. A fixed
        baseline A would also yield 1.0."""
        correct = {"A": [1, 0], "B": [0, 1], "C": [1, 1]}

        gaps = sc.bootstrap_gaps_vs_best(correct, seed=1, iterations=400, clusters=[1, 2])

        assert set(gaps) == {0.0, 0.5}

    def test_rejects_rows_and_clusters_of_different_length(self) -> None:
        """The correctness vectors and the cluster labels must line up."""
        correct = {"A": [1, 0], "B": [0, 1], "C": [1, 1]}

        with pytest.raises(ValueError, match="length"):
            sc.bootstrap_gaps_vs_best(correct, seed=1, iterations=10, clusters=[1])
