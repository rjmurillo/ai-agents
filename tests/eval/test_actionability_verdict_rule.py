"""The verdict rule and the look concept (owner decision D1).

Plan M1-T15, spec Eval method pass bar and kill criterion 2.

* pass:         gap >= 0.10 and ci_low > 0
* fail:         ci_high < 0.10 (only this proves the gain is below the bar)
* inconclusive: everything else

`--look 2` is the one-time extension. It widens the interval from 95 to 97.5 percent
(Bonferroni over two looks), records `look: 2`, and makes an inconclusive result final.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._actionability_arms_test_support import (
    aa,
    make_prediction,
    make_row,
    sc,
    write_jsonl_file,
)


class TestVerdictRule:
    @pytest.mark.parametrize(
        ("gap", "ci_low", "ci_high", "expected"),
        [
            (0.10, 0.01, 0.20, "pass"),
            (0.10, 1e-9, 0.10, "pass"),
            (0.25, 0.12, 0.40, "pass"),
            (0.12, 0.0, 0.30, "inconclusive"),
            (0.12, -0.05, 0.30, "inconclusive"),
            (0.30, -0.01, 0.60, "inconclusive"),
            (0.0999, 0.05, 0.20, "inconclusive"),
            (0.05, -0.10, 0.10, "inconclusive"),
            (0.05, -0.10, 0.0999, "fail"),
            (0.0999, 0.09, 0.0999, "fail"),
            (0.0, 0.0, 0.0, "fail"),
            (-0.10, -0.20, 0.05, "fail"),
        ],
        ids=[
            "gap-at-bar-ci-low-positive",
            "ci-low-barely-positive-ci-high-at-bar",
            "clear-pass",
            "ci-low-exactly-zero",
            "ci-low-negative",
            "wide-interval",
            "gap-just-under-bar-ci-high-above",
            "ci-high-exactly-at-bar-is-not-fail",
            "ci-high-just-under-bar",
            "gap-and-ci-high-under-bar-with-positive-ci-low",
            "all-zero",
            "negative-gap",
        ],
    )
    def test_the_table(self, gap: float, ci_low: float, ci_high: float, expected: str) -> None:
        """Boundaries at 0.10 for the gap and for ci_high, and at 0 for ci_low."""
        assert sc.verdict(gap, ci_low, ci_high) == expected

    def test_a_gap_under_the_bar_with_room_to_reach_it_is_not_a_fail(self) -> None:
        """The change from the old rule: a small gap is not proof the gain is below the bar."""
        assert sc.verdict(0.04, -0.06, 0.14) == "inconclusive"

    def test_the_bar_is_ten_points(self) -> None:
        """The constant the rule reads."""
        assert sc.PASS_GAP == 0.10

    def test_six_in_sixty_is_exactly_at_the_gap_boundary(self) -> None:
        """6/60 equals 0.10 with no float drift, so it passes when ci_low is positive."""
        gap = sc.gap_from_counts(36, 30, 60)

        assert sc.verdict(gap, 0.001, 0.2) == "pass"
        assert sc.verdict(gap, 0.0, 0.2) == "inconclusive"


class TestKillCriterionTwo:
    @pytest.mark.parametrize(
        ("verdict", "look", "kill_criterion_2", "final"),
        [
            ("fail", 1, "fired", True),
            ("fail", 2, "fired", True),
            ("pass", 1, "not_fired", True),
            ("pass", 2, "not_fired", True),
            ("inconclusive", 1, "pending", False),
            ("inconclusive", 2, "not_fired", True),
        ],
    )
    def test_mapping(self, verdict: str, look: int, kill_criterion_2: str, final: bool) -> None:
        """fired only on fail, pending only on a look-1 inconclusive, final after look 2."""
        assert sc.kill_criterion_2(verdict, look) == kill_criterion_2
        assert sc.is_final(verdict, look) is final


class TestLookIntervals:
    _DIFFS = [1] * 14 + [0] * 38 + [-1] * 8

    def test_percentiles_per_look(self) -> None:
        """Look 1 is 2.5 to 97.5. Look 2 is 1.25 to 98.75, a 97.5 percent interval."""
        assert sc.ci_percentiles(1) == (2.5, 97.5)
        assert sc.ci_percentiles(2) == (1.25, 98.75)

    @pytest.mark.parametrize("look", [0, 3, -1])
    def test_other_looks_are_rejected(self, look: int) -> None:
        """Only looks 1 and 2 exist."""
        with pytest.raises(ValueError, match="look"):
            sc.ci_percentiles(look)

    def test_the_look_two_interval_is_wider_on_the_same_seed(self) -> None:
        """Same resampled means, wider percentile cut, so it contains the look-1 interval."""
        low1, high1 = sc.paired_bootstrap_ci(self._DIFFS, seed=7, iterations=4000, look=1)
        low2, high2 = sc.paired_bootstrap_ci(self._DIFFS, seed=7, iterations=4000, look=2)

        assert low2 <= low1
        assert high2 >= high1
        assert (low2, high2) != (low1, high1)

    def test_look_defaults_to_one(self) -> None:
        """Existing callers keep the 95 percent interval."""
        default = sc.paired_bootstrap_ci(self._DIFFS, seed=7, iterations=500)

        assert default == sc.paired_bootstrap_ci(self._DIFFS, seed=7, iterations=500, look=1)


def _scenario(n: int, wins: int, losses: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """n heldout band rows, all scoring 0.5, so arm A says actionable and arm B says not.

    The first `wins` rows are not_actionable and C flips them right (+1 each). The next
    `losses` rows are actionable and C flips them wrong (-1 each). The rest are actionable
    and C keeps A's right answer. Gap = (wins - losses) / n.
    """
    rows, preds = [], []
    for i in range(n):
        truth = "not_actionable" if i < wins else "actionable"
        rows.append(make_row(f"H{i}", label=truth))
        if i < wins + losses:
            preds.append(make_prediction(f"H{i}", is_actionable=False, confidence=0.9))
    # One prediction that agrees with arm A, so a run with no wins or losses still has a
    # predictions file. It changes no row's correctness.
    preds.append(make_prediction(f"H{n - 1}", is_actionable=True, confidence=0.9))
    return rows, preds


def _report(n: int, wins: int, losses: int, look: int) -> dict[str, Any]:
    rows, preds = _scenario(n, wins, losses)
    return sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=11, iterations=2000, look=look)


class TestReportFields:
    def test_a_clear_gain_passes_and_is_final_at_look_one(self) -> None:
        """40 rows, 15 wins: gap 0.375 with a positive lower bound."""
        report = _report(40, 15, 0, look=1)

        assert report["verdict"] == "pass"
        assert report["look"] == 1
        assert report["final"] is True
        assert report["kill_criterion_2"] == "not_fired"

    def test_no_gain_fails_and_fires_kill_criterion_two(self) -> None:
        """C equals A everywhere: the interval is a point at 0, so ci_high < 0.10."""
        report = _report(40, 0, 0, look=1)

        assert report["gap_ci"] == [0.0, 0.0]
        assert report["verdict"] == "fail"
        assert report["final"] is True
        assert report["kill_criterion_2"] == "fired"

    def test_a_noisy_gain_is_inconclusive_and_pending_at_look_one(self) -> None:
        """10 rows, 3 wins and 1 loss: gap 0.2, but the interval reaches 0."""
        report = _report(10, 3, 1, look=1)

        assert report["gap"] == pytest.approx(0.2)
        assert report["gap_ci"][0] <= 0
        assert report["verdict"] == "inconclusive"
        assert report["final"] is False
        assert report["kill_criterion_2"] == "pending"

    def test_the_same_data_at_look_two_is_final_and_not_fired(self) -> None:
        """The extension is a one-time look: inconclusive here ends the question."""
        report = _report(10, 3, 1, look=2)

        assert report["look"] == 2
        assert report["verdict"] == "inconclusive"
        assert report["final"] is True
        assert report["kill_criterion_2"] == "not_fired"

    def test_the_look_two_interval_contains_the_look_one_interval(self) -> None:
        """Same seed and data: widening only moves the bounds outward."""
        one = _report(60, 9, 3, look=1)["gap_ci"]
        two = _report(60, 9, 3, look=2)["gap_ci"]

        assert two[0] <= one[0]
        assert two[1] >= one[1]
        assert two != one

    def test_the_report_states_the_interval_level(self) -> None:
        """95 percent at look 1, 97.5 percent at look 2."""
        assert _report(10, 3, 1, look=1)["gap_ci_level"] == 0.95
        assert _report(10, 3, 1, look=2)["gap_ci_level"] == 0.975

    def test_an_invalid_look_is_a_score_input_error(self) -> None:
        """build_report refuses a look it does not know."""
        rows, preds = _scenario(10, 3, 1)

        with pytest.raises(sc.ScoreInputError, match="look"):
            sc.build_report(rows, preds, aa.ARM_FUNCTIONS, seed=1, iterations=10, look=3)


def _score_argv(tmp_path: Path, n: int, wins: int, losses: int, *extra: str) -> list[str]:
    rows, preds = _scenario(n, wins, losses)
    corpus = write_jsonl_file(tmp_path / "c.jsonl", rows)
    predictions = write_jsonl_file(tmp_path / "p.jsonl", preds)
    argv = ["score", "--corpus", str(corpus), "--predictions", str(predictions)]
    return [
        *argv,
        "--output",
        str(tmp_path / "report.json"),
        "--bootstrap",
        "2000",
        "--seed",
        "11",
        *extra,
    ]


class TestScoreCliLook:
    def test_look_defaults_to_one_and_is_recorded(self, tmp_path: Path) -> None:
        """No flag means look 1."""
        code = aa.main(_score_argv(tmp_path, 10, 3, 1))

        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        assert code == 0
        assert report["look"] == 1
        assert report["kill_criterion_2"] == "pending"

    def test_look_two_is_recorded_and_final(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`--look 2` records look 2 and a final, not-fired result for an inconclusive gap."""
        code = aa.main(_score_argv(tmp_path, 10, 3, 1, "--look", "2"))

        report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
        out = capsys.readouterr().out
        assert code == 0
        assert report["look"] == 2
        assert report["final"] is True
        assert report["kill_criterion_2"] == "not_fired"
        assert "look 2" in out
        assert "kill criterion 2 not_fired" in out

    @pytest.mark.parametrize("look", ["3", "0", "-1", "10"])
    def test_any_other_look_exits_two_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], look: str
    ) -> None:
        """Only looks 1 and 2 exist."""
        code = aa.main(_score_argv(tmp_path, 10, 3, 1, "--look", look))

        assert code == 2
        assert not (tmp_path / "report.json").exists()
        assert "--look" in capsys.readouterr().err

    def test_a_fail_through_main_names_kill_criterion_two_fired(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Exit code stays 0: a verdict is a result, not an error."""
        code = aa.main(_score_argv(tmp_path, 40, 0, 0))

        assert code == 0
        assert "kill criterion 2 fired" in capsys.readouterr().out
