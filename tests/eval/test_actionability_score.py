"""Tests for the statistics and report code in scripts/eval/actionability_score.py.

Plan M1-T15. Shared helpers: _actionability_arms_test_support.py.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import aa, make_prediction, make_row, sc


class TestMetrics:
    def test_counts_give_accuracy_precision_and_recall(self) -> None:
        """Plan M1-T15: positive class is actionable."""
        result = sc.metrics([True, True, False, False], [True, False, True, False])

        assert result == {"n": 4, "accuracy": 0.5, "precision": 0.5, "recall": 0.5}

    def test_perfect_predictions(self) -> None:
        """Plan M1-T15: all correct scores 1.0 everywhere."""
        result = sc.metrics([True, False, True], [True, False, True])

        assert result == {"n": 3, "accuracy": 1.0, "precision": 1.0, "recall": 1.0}

    def test_precision_is_null_when_nothing_is_predicted_positive(self) -> None:
        """Plan M1-T15: a zero denominator is null, not 0."""
        result = sc.metrics([False, False], [True, False])

        assert result["precision"] is None
        assert result["recall"] == 0.0

    def test_recall_is_null_when_no_row_is_truly_positive(self) -> None:
        """Plan M1-T15: a zero denominator is null, not 0."""
        result = sc.metrics([True, False], [False, False])

        assert result["recall"] is None
        assert result["precision"] == 0.0

    def test_empty_input_is_all_null_with_n_zero(self) -> None:
        """Plan M1-T15: no rows means no accuracy."""
        assert sc.metrics([], []) == {"n": 0, "accuracy": None, "precision": None, "recall": None}

    def test_length_mismatch_raises(self) -> None:
        """Plan M1-T15: misaligned inputs are a caller bug."""
        with pytest.raises(ValueError, match="length"):
            sc.metrics([True], [True, False])


class TestNearestRank:
    def test_p50_and_p95_of_one_to_ten(self) -> None:
        """Plan M1-T15: nearest rank is ceil(p/100 * n)."""
        values = [float(v) for v in range(1, 11)]

        assert sc.nearest_rank(values, 50) == 5.0
        assert sc.nearest_rank(values, 95) == 10.0

    def test_input_order_does_not_matter(self) -> None:
        """Plan M1-T15: the function sorts."""
        assert sc.nearest_rank([9.0, 1.0, 5.0, 3.0, 7.0], 50) == 5.0

    def test_single_value_is_every_percentile(self) -> None:
        """Plan M1-T15: one latency is p50 and p95."""
        assert sc.nearest_rank([0.4], 50) == 0.4
        assert sc.nearest_rank([0.4], 95) == 0.4

    def test_empty_is_null(self) -> None:
        """Plan M1-T15: no ok predictions means no latency."""
        assert sc.nearest_rank([], 50) is None


class TestMinimumDetectableGap:
    def test_matches_the_formula(self) -> None:
        """Plan M1-T15: (1.96 + 0.8416) * sqrt(discordance / n)."""
        expected = (1.96 + 0.8416) * math.sqrt(0.2 / 60)

        assert sc.min_detectable_gap(60, 0.2) == pytest.approx(expected)

    def test_shrinks_as_n_grows(self) -> None:
        """Plan M1-T15: more rows detect a smaller gap."""
        assert sc.min_detectable_gap(160, 0.2) < sc.min_detectable_gap(60, 0.2)

    def test_zero_rows_is_null(self) -> None:
        """Plan M1-T15: n=0 has no detectable gap."""
        assert sc.min_detectable_gap(0, 0.2) is None


class TestPairedBootstrap:
    _DIFFS = [1] * 14 + [0] * 38 + [-1] * 8

    def _point(self) -> float:
        return sum(self._DIFFS) / len(self._DIFFS)

    def test_same_seed_gives_the_same_interval(self) -> None:
        """Plan M1-T15: the bootstrap is reproducible."""
        first = sc.paired_bootstrap_ci(self._DIFFS, seed=7, iterations=2000)
        second = sc.paired_bootstrap_ci(self._DIFFS, seed=7, iterations=2000)

        assert first == second

    def test_the_seed_drives_the_resampling(self) -> None:
        """Plan M1-T15: with few iterations, different seeds give different intervals.

        Endpoints are multiples of 1/n, so two seeds can tie at high iteration counts.
        Three iterations make a tie across eight seeds impossible to sustain.
        """
        intervals = {
            sc.paired_bootstrap_ci(self._DIFFS, seed=seed, iterations=3) for seed in range(1, 9)
        }

        assert len(intervals) > 1

    def test_interval_contains_the_point_gap(self) -> None:
        """Plan M1-T15: a 95 percent interval brackets the observed gap here."""
        low, high = sc.paired_bootstrap_ci(self._DIFFS, seed=7, iterations=5000)

        assert low <= self._point() <= high
        assert low < high

    def test_all_wins_collapse_to_a_point(self) -> None:
        """Plan M1-T15: no variation, no spread."""
        assert sc.paired_bootstrap_ci([1] * 10, seed=1, iterations=200) == (1.0, 1.0)

    def test_all_ties_collapse_to_zero(self) -> None:
        """Plan M1-T15: C and the baseline agree everywhere."""
        assert sc.paired_bootstrap_ci([0] * 10, seed=1, iterations=200) == (0.0, 0.0)

    def test_empty_is_null(self) -> None:
        """Plan M1-T15: no rows, no interval."""
        assert sc.paired_bootstrap_ci([], seed=1, iterations=200) is None


class TestVerdict:
    def test_pass_needs_a_ten_point_gap_and_a_positive_lower_bound(self) -> None:
        """Plan M1-T15 and spec pass bar."""
        assert sc.verdict(0.10, 0.01) == "pass"
        assert sc.verdict(0.25, 0.12) == "pass"

    def test_gap_at_the_bar_with_a_straddling_interval_is_inconclusive(self) -> None:
        """Plan M1-T15 and spec: CI straddles 0 with gap >= 10 points is inconclusive."""
        assert sc.verdict(0.10, 0.0) == "inconclusive"
        assert sc.verdict(0.18, -0.03) == "inconclusive"

    def test_gap_under_the_bar_fails_even_with_a_positive_interval(self) -> None:
        """Plan M1-T15: 9.99 points does not meet a 10 point bar."""
        assert sc.verdict(0.0999, 0.05) == "fail"
        assert sc.verdict(-0.1, -0.2) == "fail"

    def test_ten_point_gap_from_counts_meets_the_bar_exactly(self) -> None:
        """Plan M1-T15: 6 of 60 rows is 0.1 with no float drift."""
        assert sc.gap_from_counts(36, 30, 60) == 0.1
        assert sc.verdict(sc.gap_from_counts(36, 30, 60), 0.02) == "pass"


def _labeled(row_id: str, truth: str, **kwargs: Any) -> dict[str, Any]:
    return make_row(row_id, label=truth, **kwargs)


def _report(
    rows: list[dict[str, Any]], predictions: list[dict[str, Any]], **kwargs: Any
) -> dict[str, Any]:
    options = {"seed": 5, "iterations": 300}
    options.update(kwargs)
    return sc.build_report(rows, predictions, aa.ARM_FUNCTIONS, **options)


def _band_fixture() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Ten heldout band rows. A is right on 5, B on 5 of different rows, C overrides on 4."""
    rows = [
        _labeled("H0", "actionable"),
        _labeled("H1", "actionable"),
        _labeled("H2", "actionable"),
        _labeled("H3", "not_actionable"),
        _labeled("H4", "not_actionable"),
        _labeled("H5", "not_actionable"),
        _labeled("H6", "not_actionable"),
        _labeled("H7", "actionable"),
        _labeled("H8", "actionable"),
        _labeled("H9", "not_actionable"),
    ]
    predictions = [
        make_prediction("H3", is_actionable=False, confidence=0.9),
        make_prediction("H4", is_actionable=False, confidence=0.9),
        make_prediction("H5", is_actionable=False, confidence=0.9),
        make_prediction("H6", is_actionable=False, confidence=0.9),
    ]
    return rows, predictions


class TestBuildReport:
    def test_scores_the_three_arms_on_the_heldout_band(self) -> None:
        """Plan M1-T15: all rows score 0.5, so A says actionable and B says not."""
        rows, predictions = _band_fixture()

        report = _report(rows, predictions)

        band = report["heldout_band"]
        assert band["n"] == 10
        assert band["arms"]["A"]["accuracy"] == 0.5
        assert band["arms"]["B"]["accuracy"] == 0.5
        assert band["arms"]["C"]["accuracy"] == 0.9

    def test_tie_between_baselines_picks_arm_a(self) -> None:
        """Plan M1-T15: a tie goes to A."""
        rows, predictions = _band_fixture()

        report = _report(rows, predictions)

        assert report["best_baseline"] == "A"

    def test_arm_b_is_best_baseline_when_it_has_higher_accuracy(self) -> None:
        """Plan M1-T15: best_baseline follows heldout band accuracy."""
        rows = [_labeled(f"H{i}", "not_actionable") for i in range(4)]

        report = _report(rows, [make_prediction("H0", is_actionable=False, confidence=0.9)])

        assert report["best_baseline"] == "B"
        assert report["heldout_band"]["arms"]["B"]["accuracy"] == 1.0

    def test_gap_is_arm_c_minus_the_best_baseline(self) -> None:
        """Plan M1-T15: gap = acc(C) - acc(best)."""
        rows, predictions = _band_fixture()

        report = _report(rows, predictions)

        assert report["gap"] == pytest.approx(0.4)
        low, high = report["gap_ci"]
        assert low <= report["gap"] <= high

    def test_report_is_reproducible_for_a_seed(self) -> None:
        """Plan M1-T15: same inputs and seed, same report."""
        rows, predictions = _band_fixture()

        assert _report(rows, predictions) == _report(rows, predictions)

    def test_verdict_reflects_gap_and_interval(self) -> None:
        """Plan M1-T15: the headline field."""
        rows, predictions = _band_fixture()

        report = _report(rows, predictions, iterations=2000)

        assert report["verdict"] in {"pass", "inconclusive"}
        assert report["gap"] >= 0.10

    def test_minimum_detectable_gap_reports_assumed_and_observed_discordance(self) -> None:
        """Plan M1-T15: 0.1, 0.2, 0.3 plus the observed C-versus-best discordance."""
        rows, predictions = _band_fixture()

        report = _report(rows, predictions)

        mdg = report["minimum_detectable_gap"]
        assert set(mdg["assumed"]) == {"0.1", "0.2", "0.3"}
        assert mdg["assumed"]["0.2"] == pytest.approx(sc.min_detectable_gap(10, 0.2))
        assert mdg["observed"]["discordance"] == pytest.approx(0.4)
        assert mdg["observed"]["gap"] == pytest.approx(sc.min_detectable_gap(10, 0.4))

    def test_unsure_rows_are_dropped_and_counted(self) -> None:
        """Plan M1-T15: unsure leaves the scored set."""
        rows, predictions = _band_fixture()
        rows[0]["label"] = "unsure"

        report = _report(rows, predictions)

        assert report["labels"]["unsure_dropped"] == 1
        assert report["heldout_band"]["n"] == 9

    def test_null_label_is_rejected_with_the_unlabeled_count(self) -> None:
        """Plan M1-T15: every row must be labeled."""
        rows, predictions = _band_fixture()
        rows[0]["label"] = None
        rows[1]["label"] = None

        with pytest.raises(sc.ScoreInputError, match="2 unlabeled"):
            _report(rows, predictions)

    def test_unknown_label_value_is_rejected(self) -> None:
        """Plan M1-T15: only the three rubric values are accepted."""
        rows, predictions = _band_fixture()
        rows[0]["label"] = "maybe"

        with pytest.raises(sc.ScoreInputError, match="invalid"):
            _report(rows, predictions)

    def test_dev_rows_are_excluded_from_both_subsets(self) -> None:
        """Plan M1-T15: dev was used to tune the prompt, so it never scores."""
        rows, predictions = _band_fixture()
        rows.append(_labeled("D0", "actionable", split="dev"))

        report = _report(rows, predictions)

        assert report["heldout_band"]["n"] == 10
        assert report["non_dev"]["n"] == 10

    def test_non_dev_subset_adds_outside_rows_and_arm_c_equals_a_there(self) -> None:
        """Plan M1-T15: out-of-band rows never call the model."""
        rows, predictions = _band_fixture()
        rows.append(_labeled("O0", "actionable", split="outside", in_band=False, score=0.9))
        rows.append(_labeled("O1", "not_actionable", split="outside", in_band=False, score=0.1))

        report = _report(rows, predictions)

        assert report["non_dev"]["n"] == 12
        outside_c = report["non_dev"]["arms"]["C"]["accuracy"]
        assert outside_c == pytest.approx((9 + 2) / 12)

    def test_missing_predictions_are_counted_as_their_own_number(self) -> None:
        """Premortem R2: a silent fallback to arm A must be visible."""
        rows, predictions = _band_fixture()

        report = _report(rows, predictions)

        assert report["predictions"] == {
            "ok": 4,
            "parse_error": 0,
            "call_error": 0,
            "auth_error": 0,
            "missing": 6,
        }

    def test_failed_predictions_are_counted_by_status(self) -> None:
        """Premortem R2: failure counts are in the report."""
        rows, _ = _band_fixture()
        predictions = [
            make_prediction("H0"),
            make_prediction("H1", status="parse_error", is_actionable=None, confidence=None),
            make_prediction("H2", status="call_error", is_actionable=None, confidence=None),
        ]

        report = _report(rows, predictions)

        assert report["predictions"]["ok"] == 1
        assert report["predictions"]["parse_error"] == 1
        assert report["predictions"]["call_error"] == 1
        assert report["predictions"]["missing"] == 7

    def test_latency_percentiles_come_from_ok_predictions_only(self) -> None:
        """Plan M1-T15: failed calls do not set latency."""
        rows, _ = _band_fixture()
        predictions = [make_prediction(f"H{i}", latency_s=float(i + 1)) for i in range(4)] + [
            make_prediction("H4", status="call_error", is_actionable=None, latency_s=99.0)
        ]

        report = _report(rows, predictions)

        assert report["latency_s"] == {"p50": 2.0, "p95": 4.0, "n_ok": 4}

    def test_latency_is_null_without_ok_predictions(self) -> None:
        """Plan M1-T15: no ok call, no latency."""
        rows, _ = _band_fixture()
        predictions = [make_prediction("H0", status="call_error", is_actionable=None)]

        report = _report(rows, predictions)

        assert report["latency_s"] == {"p50": None, "p95": None, "n_ok": 0}

    def test_provenance_is_copied_from_the_predictions(self) -> None:
        """Plan M1-T15: provider, model, and prompt hash are in the report."""
        rows, predictions = _band_fixture()

        report = _report(rows, predictions)

        assert report["provider"] == "fake"
        assert report["model"] == "fake-model"
        assert report["prompt_sha256"] == "p" * 64

    @pytest.mark.parametrize("field", ["prompt_sha256", "model", "provider"])
    def test_mixed_provenance_is_rejected(self, field: str) -> None:
        """Plan M1-T15: one report, one prompt, one model, one provider."""
        rows, predictions = _band_fixture()
        predictions[0][field] = "different"

        with pytest.raises(sc.ScoreInputError, match=field):
            _report(rows, predictions)

    def test_duplicate_prediction_ids_are_rejected(self) -> None:
        """Plan M1-T15: two records for one row are ambiguous."""
        rows, predictions = _band_fixture()
        predictions.append(make_prediction("H3"))

        with pytest.raises(sc.ScoreInputError, match="duplicate"):
            _report(rows, predictions)

    def test_no_predictions_at_all_is_rejected(self) -> None:
        """Plan M1-T15: with none, arm C would silently equal arm A."""
        rows, _ = _band_fixture()

        with pytest.raises(sc.ScoreInputError, match="no predictions"):
            _report(rows, [])

    def test_no_heldout_band_rows_is_rejected(self) -> None:
        """Plan M1-T15: nothing to measure the gap on."""
        rows = [_labeled("D0", "actionable", split="dev")]

        with pytest.raises(sc.ScoreInputError, match="heldout band"):
            _report(rows, [make_prediction("D0")])

    def test_report_is_json_serializable(self) -> None:
        """Plan M1-T15: the report is written as JSON."""
        rows, predictions = _band_fixture()

        text = json.dumps(_report(rows, predictions))

        assert json.loads(text)["verdict"]
