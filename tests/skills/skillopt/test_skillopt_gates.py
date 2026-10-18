"""Tests for the skillopt scalar gate, Pareto pair gate, and scoring."""

from __future__ import annotations

from typing import Any, ClassVar, cast

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
    SHA: ClassVar[dict[str, str]] = {"incumbent_sha256": "a" * 64, "null_sha256": "a" * 64}
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
        report = skillopt.pair_gate(
            self.EVAL, self.BASE, self.ALL_PASS, null_results=null, **self.SHA
        )
        assert report["verdict"] == "REJECT_UNVERIFIED"
        assert report["unverified"] == ["ctx"]

    def test_null_reproducing_the_only_gain_is_rejected(self) -> None:
        null = {"s1": True, "s2": True, "ctx": True}
        report = skillopt.pair_gate(
            self.EVAL, self.BASE, self.ALL_PASS, null_results=null, **self.SHA
        )
        assert report["verdict"] == "REJECT_NULL_CONTROL"
        assert report["accepted"] is False
        assert report["gains"] == ["ctx"]
        assert report["null_gains"] == ["ctx"]
        assert report["genuine_gains"] == []

    def test_null_regression_without_genuine_gain_is_rejected(self) -> None:
        null = {"s1": False, "s2": True, "ctx": False}
        report = skillopt.pair_gate(
            self.EVAL, self.BASE, dict(self.BASE), null_results=null, **self.SHA
        )
        assert report["verdict"] == "REJECT_NULL_CONTROL"
        assert report["null_regressions"] == ["s1"]

    def test_null_flip_on_unrelated_task_with_genuine_gain_accepts(self) -> None:
        incumbent = {"s1": True, "s2": False, "ctx": False}
        null = {"s1": True, "s2": True, "ctx": False}  # noise: s2 flipped
        candidate = {"s1": True, "s2": True, "ctx": True}
        report = skillopt.pair_gate(self.EVAL, incumbent, candidate, null_results=null, **self.SHA)
        assert report["verdict"] == "ACCEPT_PARETO"
        assert report["accepted"] is True
        assert report["gains"] == ["s2", "ctx"]
        assert report["null_gains"] == ["s2"]
        assert report["genuine_gains"] == ["ctx"]
        assert report["null_regressions"] == []

    def test_quiet_null_control_with_gain_accepts(self) -> None:
        report = skillopt.pair_gate(
            self.EVAL, self.BASE, self.ALL_PASS, null_results=dict(self.BASE), **self.SHA
        )
        assert report["verdict"] == "ACCEPT_PARETO"
        assert report["genuine_gains"] == ["ctx"]
        assert list(report)[-3:] == ["null_gains", "null_regressions", "genuine_gains"]

    def test_quiet_null_control_without_gain_rejects(self) -> None:
        report = skillopt.pair_gate(
            self.EVAL, self.BASE, dict(self.BASE), null_results=dict(self.BASE), **self.SHA
        )
        assert report["verdict"] == "REJECT"

    def test_genuine_gain_with_regression_still_rejects_under_null(self) -> None:
        incumbent = {"s1": True, "s2": False, "ctx": False}
        candidate = {"s1": False, "s2": False, "ctx": True}
        report = skillopt.pair_gate(
            self.EVAL, incumbent, candidate, null_results=dict(incumbent), **self.SHA
        )
        assert report["verdict"] == "REJECT"
        assert report["regressions"] == ["s1"]

    def test_ceiling_when_incumbent_passes_every_sel_task(self) -> None:
        report = skillopt.pair_gate(self.EVAL, self.ALL_PASS, dict(self.ALL_PASS))
        assert report["accepted"] is False
        assert report["verdict"] == "REJECT_CEILING"
        assert (report["incumbent_passes"], report["selection_tasks"]) == (3, 3)
        assert report["gains"] == []
        assert report["regressions"] == []
        assert list(report)[-1] == "hint"
        assert "harder sel tasks" in report["hint"]
        assert "skillforge" in report["hint"]

    def test_ceiling_with_single_sel_task(self) -> None:
        report = skillopt.pair_gate({"splits": {"sel": ["a"]}}, {"a": True}, {"a": True})
        assert report["verdict"] == "REJECT_CEILING"

    def test_ceiling_with_train_gain_still_ceiling_on_sel(self) -> None:
        eval_set = {"splits": {"sel": ["a", "b"], "train": ["t"]}}
        sel = skillopt.pair_gate(
            eval_set, {"a": True, "b": True}, {"a": True, "b": True, "t": True}
        )
        train = skillopt.pair_gate(eval_set, {"t": False}, {"t": True}, split="train")
        assert sel["verdict"] == "REJECT_CEILING"
        assert train["verdict"] == "ACCEPT_PARETO"

    def test_no_ceiling_when_incumbent_below_full_pass(self) -> None:
        report = skillopt.pair_gate(self.EVAL, self.BASE, dict(self.BASE))
        assert report["verdict"] == "REJECT"
        assert "hint" not in report

    def test_no_ceiling_when_candidate_regresses(self) -> None:
        candidate = {"s1": True, "s2": False, "ctx": True}
        report = skillopt.pair_gate(self.EVAL, self.ALL_PASS, candidate)
        assert report["verdict"] == "REJECT"
        assert report["regressions"] == ["s2"]
        assert "hint" not in report

    def test_train_split_never_reports_ceiling(self) -> None:
        eval_set = {"splits": {"sel": ["a"], "train": ["t"]}}
        report = skillopt.pair_gate(eval_set, {"t": True}, {"t": True}, split="train")
        assert report["verdict"] == "REJECT"
        assert "hint" not in report

    def test_unverified_outranks_ceiling(self) -> None:
        candidate = {**self.ALL_PASS, "ctx": "UNVERIFIED"}
        report = skillopt.pair_gate(self.EVAL, self.ALL_PASS, candidate)
        assert report["verdict"] == "REJECT_UNVERIFIED"
        assert "hint" not in report

    def test_null_control_outranks_ceiling(self) -> None:
        null = {"s1": True, "s2": True, "ctx": False}
        report = skillopt.pair_gate(
            self.EVAL, self.ALL_PASS, dict(self.ALL_PASS), null_results=null, **self.SHA
        )
        assert report["null_regressions"] == ["ctx"]
        assert report["verdict"] == "REJECT_NULL_CONTROL"
        assert "hint" not in report

    def test_quiet_null_control_at_ceiling_reports_ceiling(self) -> None:
        report = skillopt.pair_gate(
            self.EVAL, self.ALL_PASS, dict(self.ALL_PASS), null_results=dict(self.ALL_PASS),
            **self.SHA,
        )  # fmt: skip
        assert report["verdict"] == "REJECT_CEILING"
        assert list(report)[-1] == "hint"

    def test_exposed_sel_task_still_raises_at_ceiling(self) -> None:
        eval_set = {"splits": {"sel": ["a"]}, "exposed": ["a"]}
        with pytest.raises(SkillOptError, match="exposed or invalid"):
            skillopt.pair_gate(eval_set, {"a": True}, {"a": True})

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

    def test_exposed_tasks_moved_to_train_still_report_regressions(self) -> None:
        eval_set = {"splits": {"sel": ["s1"], "train": ["leak"]}, "exposed": ["leak"]}
        report = skillopt.pair_gate(eval_set, {"leak": True}, {"leak": False}, split="train")
        assert report["regressions"] == ["leak"]

    @pytest.mark.parametrize("status", [["invalid"], 5, True, None])
    def test_non_string_status_errors(self, status: object) -> None:
        eval_set = {**self.EVAL, "tasks": {"s1": {"status": status}}}
        with pytest.raises(SkillOptError, match="status must be a string"):
            skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)

    def test_entry_without_status_is_fine(self) -> None:
        eval_set = {**self.EVAL, "tasks": {"s1": {"note": "x"}}}
        assert skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)["accepted"] is True

    @pytest.mark.parametrize("tasks", [["s1"], "s1", None, 5])
    def test_non_dict_tasks_block_errors(self, tasks: object) -> None:
        eval_set = {**self.EVAL, "tasks": tasks}
        with pytest.raises(SkillOptError, match="'tasks' must be an object"):
            skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)

    @pytest.mark.parametrize("entry", ["invalid", None, 3])
    def test_non_dict_task_entry_is_ignored(self, entry: object) -> None:
        eval_set = {**self.EVAL, "tasks": {"s1": entry}}
        assert skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)["accepted"] is True

    def test_exposed_and_bad_tasks_outside_sel_do_not_block_train_review(self) -> None:
        eval_set = {
            "splits": {"sel": ["a"], "train": ["leaked", "bad"]},
            "exposed": ["leaked"],
            "tasks": {"bad": {"status": "invalid"}, "leaked": {"status": "exposed"}},
        }
        incumbent = {"leaked": False, "bad": False}
        candidate = {"leaked": True, "bad": False}
        report = skillopt.pair_gate(eval_set, incumbent, candidate, split="train")
        assert report["verdict"] == "ACCEPT_PARETO"

    def test_malformed_tasks_block_ignored_off_sel(self) -> None:
        eval_set = {"splits": {"train": ["t"]}, "tasks": ["junk"], "exposed": "junk"}
        assert skillopt.pair_gate(eval_set, {"t": False}, {"t": True}, split="train")["accepted"]

    # --- null-control provenance ---
    @pytest.mark.parametrize(
        ("inc", "nul"),
        [
            (None, None),
            ("a" * 64, None),
            (None, "a" * 64),
            ("zz", "zz"),
            (5, 5),
            ("a" * 63, "a" * 63),
        ],
    )
    def test_null_results_need_both_hashes(self, inc: object, nul: object) -> None:
        with pytest.raises(SkillOptError, match="needs --incumbent-sha256 and --null-sha256"):
            skillopt.pair_gate(
                self.EVAL,
                self.BASE,
                self.ALL_PASS,
                null_results=dict(self.BASE),
                incumbent_sha256=cast(Any, inc),
                null_sha256=cast(Any, nul),
            )

    def test_null_hash_mismatch_errors(self) -> None:
        with pytest.raises(SkillOptError, match="did not run on the byte-identical incumbent"):
            skillopt.pair_gate(
                self.EVAL,
                self.BASE,
                self.ALL_PASS,
                null_results=dict(self.BASE),
                incumbent_sha256="a" * 64,
                null_sha256="b" * 64,
            )

    def test_null_hash_comparison_ignores_case_and_whitespace(self) -> None:
        report = skillopt.pair_gate(
            self.EVAL,
            self.BASE,
            self.ALL_PASS,
            null_results=dict(self.BASE),
            incumbent_sha256="ab" * 32,
            null_sha256=" " + "AB" * 32 + "\n",
        )
        assert report["accepted"] is True

    def test_hashes_without_null_results_are_ignored(self) -> None:
        report = skillopt.pair_gate(
            self.EVAL, self.BASE, self.ALL_PASS, incumbent_sha256="a" * 64, null_sha256="a" * 64
        )
        assert "null_gains" not in report

    # --- scorer declaration ---
    def test_nondeterministic_scorer_requires_null_results(self) -> None:
        eval_set = {**self.EVAL, "scorer": "nondeterministic"}
        with pytest.raises(SkillOptError, match="nondeterministic scorer requires --null-results"):
            skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)

    def test_nondeterministic_scorer_with_null_results_runs(self) -> None:
        eval_set = {**self.EVAL, "scorer": "nondeterministic"}
        report = skillopt.pair_gate(
            eval_set, self.BASE, self.ALL_PASS, null_results=dict(self.BASE), **self.SHA
        )
        assert report["accepted"] is True

    def test_nondeterministic_scorer_off_sel_needs_no_null(self) -> None:
        eval_set = {"splits": {"train": ["t"]}, "scorer": "nondeterministic"}
        assert skillopt.pair_gate(eval_set, {"t": False}, {"t": True}, split="train")["accepted"]

    def test_deterministic_scorer_needs_no_null(self) -> None:
        eval_set = {**self.EVAL, "scorer": "deterministic"}
        assert skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)["accepted"] is True

    @pytest.mark.parametrize("scorer", ["Deterministic", "random", 5, True, ["deterministic"], {}])
    def test_unknown_scorer_errors(self, scorer: object) -> None:
        eval_set = {**self.EVAL, "scorer": scorer}
        with pytest.raises(SkillOptError, match="'scorer' must be one of"):
            skillopt.pair_gate(eval_set, self.BASE, self.ALL_PASS)

    def test_unknown_scorer_errors_off_sel_too(self) -> None:
        eval_set = {"splits": {"train": ["t"]}, "scorer": "random"}
        with pytest.raises(SkillOptError, match="'scorer' must be one of"):
            skillopt.pair_gate(eval_set, {}, {}, split="train")

    def test_null_scorer_value_is_absent(self) -> None:
        eval_set = {**self.EVAL, "scorer": None}
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
