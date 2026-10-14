"""Tests for the skillopt scalar gate, Pareto pair gate, and scoring."""

from __future__ import annotations

import pytest
import skillopt
from skillopt import SkillOptError


class TestGate:
    def test_strictly_greater_accepts(self) -> None:
        assert skillopt.gate(0.81, 0.80) is True

    def test_equal_rejects(self) -> None:
        assert skillopt.gate(0.80, 0.80) is False

    def test_less_rejects(self) -> None:
        assert skillopt.gate(0.79, 0.80) is False


class TestPairGate:
    EVAL = {"splits": {"sel": ["s1", "s2", "ctx"]}}
    ALL_PASS = {"s1": True, "s2": True, "ctx": True}
    BASE = {"s1": True, "s2": True, "ctx": False}

    def test_accepts_gain_with_no_regression(self) -> None:
        report = skillopt.pair_gate(self.EVAL, self.BASE, self.ALL_PASS)
        assert report["accepted"] is True
        assert report["verdict"] == "ACCEPT_PARETO"
        assert report["gains"] == ["ctx"]
        assert report["regressions"] == []
        assert report["unverified"] == []
        assert "null_gains" not in report

    def test_report_keys_without_null(self) -> None:
        report = skillopt.pair_gate(self.EVAL, self.BASE, self.ALL_PASS)
        assert list(report) == [
            "accepted", "verdict", "split", "selection_tasks", "incumbent_passes",
            "candidate_passes", "gains", "regressions", "unverified",
        ]  # fmt: skip
        assert report["selection_tasks"] == 3
        assert (report["incumbent_passes"], report["candidate_passes"]) == (2, 3)

    def test_rejects_tie(self) -> None:
        report = skillopt.pair_gate(self.EVAL, self.BASE, dict(self.BASE))
        assert report["accepted"] is False
        assert report["verdict"] == "REJECT"
        assert report["gains"] == []

    def test_rejects_any_regression_even_with_gains(self) -> None:
        incumbent = {"s1": True, "s2": False, "ctx": False}
        candidate = {"s1": False, "s2": True, "ctx": True}
        report = skillopt.pair_gate(self.EVAL, incumbent, candidate)
        assert report["candidate_passes"] > report["incumbent_passes"]
        assert report["accepted"] is False
        assert report["verdict"] == "REJECT"
        assert report["regressions"] == ["s1"]

    def test_missing_candidate_result_is_regression_and_unverified(self) -> None:
        report = skillopt.pair_gate(self.EVAL, {"s1": True, "s2": True, "ctx": True}, {})
        assert report["regressions"] == ["s1", "s2", "ctx"]
        assert report["verdict"] == "REJECT_UNVERIFIED"
        assert report["unverified"] == ["s1", "s2", "ctx"]

    @pytest.mark.parametrize("bad", ["UNVERIFIED", "INVALID", 1, 0, None, [], {}])
    def test_non_bool_candidate_value_is_unverified(self, bad: object) -> None:
        candidate = {**self.ALL_PASS, "ctx": bad}
        report = skillopt.pair_gate(self.EVAL, self.BASE, candidate)
        assert report["verdict"] == "REJECT_UNVERIFIED"
        assert report["accepted"] is False
        assert report["unverified"] == ["ctx"]
        assert report["gains"] == []  # only literal True is a pass

    def test_non_bool_incumbent_value_is_unverified(self) -> None:
        incumbent = {"s1": True, "s2": "INVALID", "ctx": False}
        report = skillopt.pair_gate(self.EVAL, incumbent, self.ALL_PASS)
        assert report["verdict"] == "REJECT_UNVERIFIED"
        assert report["unverified"] == ["s2"]

    def test_non_bool_null_value_is_unverified(self) -> None:
        null = {"s1": True, "s2": True, "ctx": "UNVERIFIED"}
        report = skillopt.pair_gate(self.EVAL, self.BASE, self.ALL_PASS, null_results=null)
        assert report["verdict"] == "REJECT_UNVERIFIED"
        assert report["unverified"] == ["ctx"]

    def test_null_reproducing_the_only_gain_is_rejected(self) -> None:
        null = {"s1": True, "s2": True, "ctx": True}
        report = skillopt.pair_gate(self.EVAL, self.BASE, self.ALL_PASS, null_results=null)
        assert report["verdict"] == "REJECT_NULL_CONTROL"
        assert report["accepted"] is False
        assert report["gains"] == ["ctx"]
        assert report["null_gains"] == ["ctx"]
        assert report["genuine_gains"] == []

    def test_null_regression_without_genuine_gain_is_rejected(self) -> None:
        null = {"s1": False, "s2": True, "ctx": False}
        report = skillopt.pair_gate(self.EVAL, self.BASE, dict(self.BASE), null_results=null)
        assert report["verdict"] == "REJECT_NULL_CONTROL"
        assert report["null_regressions"] == ["s1"]

    def test_null_flip_on_unrelated_task_with_genuine_gain_accepts(self) -> None:
        incumbent = {"s1": True, "s2": False, "ctx": False}
        null = {"s1": True, "s2": True, "ctx": False}  # noise: s2 flipped
        candidate = {"s1": True, "s2": True, "ctx": True}
        report = skillopt.pair_gate(self.EVAL, incumbent, candidate, null_results=null)
        assert report["verdict"] == "ACCEPT_PARETO"
        assert report["accepted"] is True
        assert report["gains"] == ["s2", "ctx"]
        assert report["null_gains"] == ["s2"]
        assert report["genuine_gains"] == ["ctx"]
        assert report["null_regressions"] == []

    def test_quiet_null_control_with_gain_accepts(self) -> None:
        report = skillopt.pair_gate(
            self.EVAL, self.BASE, self.ALL_PASS, null_results=dict(self.BASE)
        )
        assert report["verdict"] == "ACCEPT_PARETO"
        assert report["genuine_gains"] == ["ctx"]
        assert list(report)[-3:] == ["null_gains", "null_regressions", "genuine_gains"]

    def test_quiet_null_control_without_gain_rejects(self) -> None:
        report = skillopt.pair_gate(
            self.EVAL, self.BASE, dict(self.BASE), null_results=dict(self.BASE)
        )
        assert report["verdict"] == "REJECT"

    def test_genuine_gain_with_regression_still_rejects_under_null(self) -> None:
        incumbent = {"s1": True, "s2": False, "ctx": False}
        candidate = {"s1": False, "s2": False, "ctx": True}
        report = skillopt.pair_gate(self.EVAL, incumbent, candidate, null_results=dict(incumbent))
        assert report["verdict"] == "REJECT"
        assert report["regressions"] == ["s1"]

    def test_other_split(self) -> None:
        eval_set = {"splits": {"sel": ["a"], "dev": ["b"]}}
        report = skillopt.pair_gate(eval_set, {"b": False}, {"b": True}, split="dev")
        assert report["split"] == "dev"
        assert report["verdict"] == "ACCEPT_PARETO"

    # --- split validation ---
    def test_missing_split_errors(self) -> None:
        with pytest.raises(SkillOptError, match="no 'sel' split"):
            skillopt.pair_gate({"splits": {"train": ["a"]}}, {}, {})

    def test_empty_split_errors(self) -> None:
        with pytest.raises(SkillOptError, match="vacuous"):
            skillopt.pair_gate({"splits": {"sel": []}}, {}, {})

    def test_no_splits_key_errors(self) -> None:
        with pytest.raises(SkillOptError, match="no 'sel' split"):
            skillopt.pair_gate({}, {}, {})

    # --- exposed / invalid selection tasks ---
    def test_exposed_list_errors_naming_ids(self) -> None:
        eval_set = {**self.EVAL, "exposed": ["s2", "ctx", "unrelated"]}
        with pytest.raises(SkillOptError) as exc:
            skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)
        message = str(exc.value)
        assert "selection task(s) exposed or invalid: s2, ctx;" in message
        assert "replace them with untouched holdout tasks before gating" in message
        assert "unrelated" not in message

    @pytest.mark.parametrize("status", ["invalid", "exposed"])
    def test_bad_status_errors(self, status: str) -> None:
        eval_set = {**self.EVAL, "tasks": {"s1": {"status": status}, "s2": {"status": "ok"}}}
        with pytest.raises(SkillOptError, match="exposed or invalid: s1;"):
            skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)

    def test_ok_status_and_exposed_outside_split_are_fine(self) -> None:
        eval_set = {
            **self.EVAL,
            "exposed": ["train-only"],
            "tasks": {"s1": {"status": "ok"}, "train-only": {"status": "exposed"}},
        }
        assert skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)["accepted"] is True

    def test_unhashable_status_is_not_a_crash(self) -> None:
        eval_set = {**self.EVAL, "tasks": {"s1": {"status": ["invalid"]}}}
        assert skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)["accepted"] is True

    @pytest.mark.parametrize("tasks", [["s1"], "s1", None, {"s1": "invalid"}, {"s1": None}])
    def test_malformed_tasks_block_is_ignored(self, tasks: object) -> None:
        eval_set = {**self.EVAL, "tasks": tasks}
        assert skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)["accepted"] is True

    @pytest.mark.parametrize("exposed", ["s1", {"s1": True}, 5])
    def test_non_list_exposed_errors(self, exposed: object) -> None:
        with pytest.raises(SkillOptError, match="'exposed' must be a list"):
            skillopt.pair_gate({**self.EVAL, "exposed": exposed}, self.BASE, self.ALL_PASS)


class TestScore:
    EVAL = {"splits": {"sel": ["t1", "t2", "t3", "t4"], "train": ["t5"]}}

    def test_pass_rate(self) -> None:
        results = {"t1": True, "t2": True, "t3": False, "t4": True}
        assert skillopt.score_results(self.EVAL, results) == 0.75

    def test_missing_result_counts_as_fail(self) -> None:
        assert skillopt.score_results(self.EVAL, {"t1": True}) == 0.25

    def test_non_true_value_is_fail(self) -> None:
        results = {"t1": True, "t2": "yes", "t3": 1, "t4": True}
        assert skillopt.score_results(self.EVAL, results) == 0.5

    def test_missing_split_rejected(self) -> None:
        with pytest.raises(SkillOptError) as exc:
            skillopt.score_results({"splits": {"train": ["t1"]}}, {})
        assert str(exc.value) == "eval set has no 'sel' split"

    def test_no_splits_key_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="no 'sel' split"):
            skillopt.score_results({}, {})

    def test_empty_split_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="vacuous"):
            skillopt.score_results({"splits": {"sel": []}}, {})

    def test_non_list_split_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="vacuous"):
            skillopt.score_results({"splits": {"sel": "t1"}}, {})

    def test_non_string_task_id_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="nonempty string task ids"):
            skillopt.score_results({"splits": {"sel": ["t1", 2]}}, {})

    def test_empty_string_task_id_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="nonempty string task ids"):
            skillopt.score_results({"splits": {"sel": ["t1", ""]}}, {})

    def test_duplicate_task_id_rejected(self) -> None:
        with pytest.raises(SkillOptError, match="duplicate task ids"):
            skillopt.score_results({"splits": {"sel": ["t1", "t1"]}}, {})
