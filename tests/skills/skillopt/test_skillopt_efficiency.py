"""Tests for the skillopt efficiency gate and its CLI command."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import skillopt
from skillopt import SkillOptError
from skillopt_helpers import write_json

TASKS = ("a", "b", "guard")
ALL_PASS = {"a": True, "b": True, "guard": True}


def _eval(**spec_overrides: object) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "metric": "total_tokens",
        "direction": "lower",
        "min_relative_gain": 0.10,
        "null_tolerance": 0.03,
        "min_repeats": 3,
    }
    spec.update(spec_overrides)
    return {
        "splits": {"sel": list(TASKS)},
        "tasks": {"guard": {"kind": "safety"}},
        "efficiency": spec,
    }


def _arm(value: float) -> dict[str, list[float]]:
    return {tid: [value, value, value] for tid in TASKS}


def _measurements(candidate: float = 80, null: float = 100) -> dict[str, Any]:
    return {"incumbent": _arm(100), "candidate": _arm(candidate), "null": _arm(null)}


def _gate(
    eval_set: dict[str, Any] | None = None,
    incumbent: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    measurements: dict[str, Any] | None = None,
    split: str = "sel",
) -> dict[str, Any]:
    return skillopt.efficiency_gate(
        eval_set or _eval(),
        ALL_PASS if incumbent is None else incumbent,
        ALL_PASS if candidate is None else candidate,
        measurements or _measurements(),
        split,
    )


class TestAccept:
    def test_accepts_ceiling_candidate_with_repeatable_gain(self) -> None:
        report = _gate(measurements=_measurements(candidate=80, null=101))
        assert report["accepted"] is True
        assert report["verdict"] == "ACCEPT_EFFICIENCY"
        assert report["reasons"] == []
        assert report["gain"] == pytest.approx(0.20)
        assert report["mean_gain"] == pytest.approx(0.20)
        assert report["null_gain"] == pytest.approx(-0.01)
        assert report["worst_case_gain"] == pytest.approx(0.20)
        assert report["metric"] == "total_tokens"
        assert report["selection_tasks"] == 3

    def test_accepts_higher_direction_gain(self) -> None:
        measurements = {"incumbent": _arm(100), "candidate": _arm(130), "null": _arm(100)}
        report = _gate(_eval(direction="higher"), measurements=measurements)
        assert report["accepted"] is True
        assert report["gain"] == pytest.approx(0.30)

    def test_gain_exactly_at_threshold_accepts(self) -> None:
        report = _gate(_eval(min_relative_gain=0.25), measurements=_measurements(candidate=75))
        assert report["accepted"] is True

    def test_mild_tail_keeping_mean_above_threshold_accepts(self) -> None:
        measurements = _measurements(candidate=80)
        measurements["candidate"]["a"] = [80, 80, 100]
        report = _gate(measurements=measurements)
        assert report["accepted"] is True
        assert 0.10 <= report["mean_gain"] < report["gain"]

    def test_report_keys_carry_the_declared_spec(self) -> None:
        report = _gate()
        assert report["min_relative_gain"] == 0.10
        assert report["null_tolerance"] == 0.03
        assert report["min_repeats"] == 3
        assert report["direction"] == "lower"
        assert report["split"] == "sel"


class TestCorrectnessReasons:
    def test_incumbent_below_ceiling(self) -> None:
        incumbent = {"a": True, "b": False, "guard": True}
        report = _gate(incumbent=incumbent)
        assert report["accepted"] is False
        assert report["regressions"] == []
        assert report["reasons"] == ["incumbent_below_ceiling"]

    def test_correctness_regression(self) -> None:
        report = _gate(candidate={"a": True, "b": False, "guard": True})
        assert report["regressions"] == ["b"]
        assert report["reasons"] == ["correctness_regression"]

    def test_safety_failure_even_when_incumbent_also_failed(self) -> None:
        both = {"a": True, "b": True, "guard": False}
        report = _gate(incumbent=both, candidate=both)
        assert report["safety_failures"] == ["guard"]
        assert report["reasons"] == ["incumbent_below_ceiling", "safety_failure"]

    @pytest.mark.parametrize(
        "candidate",
        [{}, {"a": True, "b": True, "guard": "yes"}, {"a": True, "b": True}],
    )
    def test_missing_or_non_boolean_candidate_is_unverified(self, candidate: dict) -> None:
        report = _gate(candidate=candidate)
        assert report["accepted"] is False
        assert "unverified_correctness" in report["reasons"]

    def test_missing_incumbent_results_list_every_task_unverified(self) -> None:
        report = _gate(incumbent={})
        assert report["unverified"] == list(TASKS)


class TestMeasurementReasons:
    def test_gain_below_threshold(self) -> None:
        report = _gate(measurements=_measurements(candidate=95))
        assert report["reasons"] == ["gain_below_threshold"]

    def test_candidate_that_costs_more(self) -> None:
        report = _gate(measurements=_measurements(candidate=120))
        assert report["accepted"] is False
        assert report["gain"] == pytest.approx(-0.20)

    def test_gain_the_null_control_also_shows(self) -> None:
        report = _gate(
            _eval(null_tolerance=0.05), measurements=_measurements(candidate=96, null=96)
        )
        assert report["reasons"] == [
            "gain_below_threshold",
            "gain_within_null",
            "mean_gain_within_null",
        ]

    @pytest.mark.parametrize("null", [90, 110])
    def test_null_wider_than_tolerance_in_either_direction(self, null: float) -> None:
        report = _gate(measurements=_measurements(candidate=50, null=null))
        assert report["reasons"] == ["null_too_wide"]

    def test_offsetting_null_outliers_on_two_tasks_still_flag_a_task(self) -> None:
        measurements = _measurements(candidate=80)
        measurements["null"]["a"] = [150, 150, 150]
        measurements["null"]["b"] = [50, 50, 50]
        report = _gate(measurements=measurements)
        assert report["accepted"] is False
        assert "null_too_wide" in report["reasons"]
        assert set(report["null_wide_tasks"]) == {"a", "b"}

    def test_median_ignores_one_outlier_repeat(self) -> None:
        measurements = _measurements(candidate=100)
        measurements["candidate"]["a"] = [1, 100, 100]
        report = _gate(measurements=measurements)
        assert report["accepted"] is False
        assert report["gain"] == pytest.approx(0.0)

    def test_heavy_upper_tail_the_median_hides(self) -> None:
        measurements = _measurements(candidate=100)
        measurements["candidate"]["a"] = [80, 80, 1000]
        measurements["candidate"]["b"] = [80, 80, 1000]
        report = _gate(measurements=measurements)
        assert report["accepted"] is False
        assert report["reasons"] == [
            "mean_gain_below_threshold",
            "mean_gain_within_null",
            "gain_within_spread",
        ]
        assert report["gain"] > 0.10
        assert report["mean_gain"] < 0

    def test_gain_inside_run_to_run_spread(self) -> None:
        measurements = _measurements(candidate=80)
        measurements["incumbent"] = {tid: [60, 100, 140] for tid in TASKS}
        measurements["candidate"] = {tid: [70, 80, 90] for tid in TASKS}
        measurements["null"] = {tid: [60, 100, 140] for tid in TASKS}
        report = _gate(measurements=measurements)
        assert report["accepted"] is False
        assert "gain_within_spread" in report["reasons"]
        assert report["worst_case_gain"] <= 0

    def test_one_task_regressing_is_not_hidden_by_a_large_task(self) -> None:
        measurements = _measurements(candidate=80)
        measurements["incumbent"]["a"] = [1000, 1000, 1000]
        measurements["null"]["a"] = [1000, 1000, 1000]
        measurements["candidate"]["a"] = [500, 500, 500]
        measurements["candidate"]["b"] = [150, 150, 150]
        report = _gate(measurements=measurements)
        assert report["accepted"] is False
        assert report["reasons"] == ["task_cost_regression"]
        assert report["task_cost_regressions"] == ["b"]

    def test_zero_incumbent_task_regresses_when_candidate_costs_anything(self) -> None:
        measurements = _measurements(candidate=80)
        for arm in ("incumbent", "null"):
            measurements[arm]["guard"] = [0, 0, 0]
        measurements["candidate"]["guard"] = [5, 5, 5]
        report = _gate(measurements=measurements)
        assert report["accepted"] is False
        assert "task_cost_regression" in report["reasons"]
        assert report["per_task_gain"]["guard"] is None

    def test_zero_incumbent_task_unchanged_does_not_regress(self) -> None:
        measurements = _measurements(candidate=80)
        for arm in ("incumbent", "null", "candidate"):
            measurements[arm]["guard"] = [0, 0, 0]
        report = _gate(measurements=measurements)
        assert report["accepted"] is True

    def test_all_zero_incumbent_is_invalid(self) -> None:
        measurements = {"incumbent": _arm(0), "candidate": _arm(0), "null": _arm(0)}
        report = _gate(measurements=measurements)
        assert report["reasons"] == ["measurements_invalid"]


class TestMeasurementShape:
    def test_missing_arm(self) -> None:
        measurements = _measurements()
        del measurements["null"]
        assert _gate(measurements=measurements)["reasons"] == ["measurements_missing"]

    def test_missing_task_in_arm(self) -> None:
        measurements = _measurements()
        del measurements["candidate"]["b"]
        assert _gate(measurements=measurements)["reasons"] == ["measurements_missing"]

    def test_empty_values_list(self) -> None:
        measurements = _measurements()
        measurements["candidate"]["b"] = []
        assert _gate(measurements=measurements)["reasons"] == ["measurements_missing"]

    @pytest.mark.parametrize("bad", [True, "5", -1, None, float("inf"), 10**400])
    def test_non_numeric_negative_or_non_finite_values(self, bad: object) -> None:
        measurements = _measurements()
        measurements["candidate"]["b"] = [80, 80, bad]
        assert _gate(measurements=measurements)["reasons"] == ["measurements_invalid"]

    def test_fewer_repeats_than_declared(self) -> None:
        measurements = _measurements()
        measurements["candidate"]["a"] = [80, 80]
        measurements["incumbent"]["a"] = [100, 100]
        measurements["null"]["a"] = [100, 100]
        assert _gate(measurements=measurements)["reasons"] == ["measurements_short"]

    def test_unequal_repeat_counts_across_arms(self) -> None:
        measurements = _measurements()
        measurements["candidate"]["a"] = [80, 80, 80, 80]
        assert _gate(measurements=measurements)["reasons"] == ["measurements_unmatched"]

    def test_arm_that_is_not_an_object(self) -> None:
        measurements = _measurements()
        measurements["candidate"] = [1, 2, 3]
        assert _gate(measurements=measurements)["reasons"] == ["measurements_missing"]

    def test_per_task_values_that_sum_past_float_range_are_invalid(self) -> None:
        """Each task mean is finite; the summed total across tasks overflows."""
        ids = ["a", "b", "guard", "d"]
        eval_set = _eval()
        eval_set["splits"]["sel"] = ids
        huge = {tid: [5e307, 5e307, 5e307] for tid in ids}
        measurements = {"incumbent": huge, "candidate": huge, "null": huge}
        passing = dict.fromkeys(ids, True)
        report = _gate(eval_set, passing, passing, measurements)
        assert report["reasons"] == ["measurements_invalid"]

    def test_incumbent_best_repeats_of_zero_make_spread_undefined(self) -> None:
        measurements = _measurements(candidate=80)
        measurements["incumbent"] = {tid: [0, 100, 100] for tid in TASKS}
        measurements["null"] = {tid: [0, 100, 100] for tid in TASKS}
        report = _gate(measurements=measurements)
        assert report["accepted"] is False
        assert report["worst_case_gain"] is None
        assert "gain_within_spread" in report["reasons"]

    def test_values_summing_past_float_range_are_invalid(self) -> None:
        huge = 1.7e308
        measurements = {
            "incumbent": {tid: [huge, huge, huge] for tid in TASKS},
            "candidate": _arm(80),
            "null": {tid: [huge, huge, huge] for tid in TASKS},
        }
        assert _gate(measurements=measurements)["reasons"] == ["measurements_invalid"]


class TestSpecValidation:
    def test_missing_efficiency_object(self) -> None:
        eval_set = _eval()
        del eval_set["efficiency"]
        with pytest.raises(SkillOptError, match="no 'efficiency' objective"):
            _gate(eval_set)

    @pytest.mark.parametrize("metric", ["", None, 5])
    def test_metric_must_be_nonempty_string(self, metric: object) -> None:
        with pytest.raises(SkillOptError, match="metric"):
            _gate(_eval(metric=metric))

    def test_direction_must_be_lower_or_higher(self) -> None:
        with pytest.raises(SkillOptError, match="direction"):
            _gate(_eval(direction="sideways"))

    @pytest.mark.parametrize("key", ["min_relative_gain", "null_tolerance"])
    @pytest.mark.parametrize("value", [0, 1, -0.1, 1.5, True, "0.1", None])
    def test_fractions_must_sit_strictly_between_zero_and_one(
        self, key: str, value: object
    ) -> None:
        with pytest.raises(SkillOptError, match=key):
            _gate(_eval(**{key: value}))

    def test_null_tolerance_must_be_below_min_gain(self) -> None:
        with pytest.raises(SkillOptError, match="null_tolerance must be below"):
            _gate(_eval(min_relative_gain=0.05, null_tolerance=0.05))

    @pytest.mark.parametrize("repeats", [2, 0, True, 3.0, "3", None])
    def test_min_repeats_must_be_an_integer_of_three_or_more(self, repeats: object) -> None:
        with pytest.raises(SkillOptError, match="min_repeats"):
            _gate(_eval(min_repeats=repeats))


class TestSplitRules:
    def test_safety_task_outside_sel_split_is_refused(self) -> None:
        eval_set = _eval()
        eval_set["splits"]["train"] = ["t1"]
        eval_set["tasks"]["t1"] = {"kind": "safety"}
        with pytest.raises(SkillOptError, match="safety tasks"):
            _gate(eval_set)

    def test_exposed_sel_task_is_refused(self) -> None:
        eval_set = _eval()
        eval_set["exposed"] = ["a"]
        with pytest.raises(SkillOptError, match="exposed or invalid"):
            _gate(eval_set)

    def test_invalid_sel_task_is_refused(self) -> None:
        eval_set = _eval()
        eval_set["tasks"]["b"] = {"status": "invalid"}
        with pytest.raises(SkillOptError, match="exposed or invalid"):
            _gate(eval_set)

    def test_train_split_may_hold_exposed_and_outside_safety_tasks(self) -> None:
        eval_set = _eval()
        eval_set["splits"]["train"] = list(TASKS)
        eval_set["exposed"] = ["a"]
        measurements = _measurements()
        report = _gate(eval_set, measurements=measurements, split="train")
        assert report["accepted"] is True
        assert report["split"] == "train"

    def test_missing_split(self) -> None:
        with pytest.raises(SkillOptError, match="no 'holdout' split"):
            _gate(split="holdout")

    def test_tasks_must_be_an_object(self) -> None:
        eval_set = _eval()
        eval_set["tasks"] = []
        with pytest.raises(SkillOptError, match="tasks"):
            _gate(eval_set)


class TestCli:
    def _files(
        self, tmp_path: Path, eval_set: dict | None = None, measurements: dict | None = None
    ) -> list[str]:
        return [
            "efficiency-gate",
            "--eval",
            str(write_json(tmp_path / "eval.json", eval_set or _eval())),
            "--incumbent-results",
            str(write_json(tmp_path / "inc.json", ALL_PASS)),
            "--candidate-results",
            str(write_json(tmp_path / "cand.json", ALL_PASS)),
            "--measurements",
            str(write_json(tmp_path / "m.json", measurements or _measurements())),
        ]

    def test_accept_exits_zero_and_prints_report(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert skillopt.main(self._files(tmp_path)) == 0
        assert json.loads(capsys.readouterr().out)["verdict"] == "ACCEPT_EFFICIENCY"

    def test_reject_exits_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        argv = self._files(tmp_path, measurements=_measurements(candidate=99))
        assert skillopt.main(argv) == 1
        assert json.loads(capsys.readouterr().out)["verdict"] == "REJECT"

    def test_missing_spec_exits_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        eval_set = copy.deepcopy(_eval())
        del eval_set["efficiency"]
        assert skillopt.main(self._files(tmp_path, eval_set)) == 2
        assert "efficiency" in capsys.readouterr().err

    def test_non_object_measurements_exit_two(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        argv = self._files(tmp_path)
        write_json(tmp_path / "m.json", [1, 2])
        assert skillopt.main(argv) == 2
        assert "must be a JSON object" in capsys.readouterr().err

    def test_missing_file_exits_two(self, tmp_path: Path) -> None:
        argv = self._files(tmp_path)
        (tmp_path / "m.json").unlink()
        assert skillopt.main(argv) == 2
