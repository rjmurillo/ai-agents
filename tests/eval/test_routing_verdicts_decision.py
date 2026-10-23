"""Tests for the decision floor, decision mapping, and row parsing (issue #5426)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.eval._routing_verdicts_test_support import (
    ALL_IDS,
    CLASSES,
    FALLBACK,
    ORDINARY,
    accept_first,
    arm_rows,
    fail_all,
    full_dataset,
    row,
    runs_of,
    v,
)

# ------------------------------------------------------------------------- decision


def statuses(
    h1: str = v.INSUFFICIENT,
    h2: str = v.INSUFFICIENT,
    h3: str = v.INSUFFICIENT,
    h4: str = v.INSUFFICIENT,
) -> dict[str, str]:
    return {"H1": h1, "H2": h2, "H3": h3, "H4": h4}


def test_one_arm_short_forces_insufficient_even_when_total_is_at_least_twelve() -> None:
    rows = full_dataset(A=arm_rows("A", ALL_IDS, accept_first(11)))
    rows = [
        r
        for r in rows
        if not (r["arm"] == "A" and r["scenario_id"] == ORDINARY[3] and r["repetition"] == 3)
    ]
    report = v.score(runs_of(rows), CLASSES)
    floor = report["decision_floor"]
    assert sum(a["scored_ordinary_runs"] for a in floor["per_arm"].values()) >= 12
    assert floor["per_arm"]["A"]["scored_ordinary_runs"] == 11
    assert floor["arms_short"] == ["A"]
    assert report["decision"] == v.INSUFFICIENT


def test_floor_counts_scored_runs_not_accepted_runs() -> None:
    rows = full_dataset(A=arm_rows("A", ALL_IDS, accept_first(5)))
    floor = v.score(runs_of(rows), CLASSES)["decision_floor"]
    assert floor["per_arm"]["A"]["scored_ordinary_runs"] == 12
    assert floor["per_arm"]["A"]["accepted_ordinary_runs"] == 5
    assert floor["per_arm"]["A"]["meets_floor"] is True
    assert floor["arms_short"] == []


def test_harness_failed_and_not_run_do_not_count_as_scored() -> None:
    a = arm_rows("A", ALL_IDS)
    a[0]["status"] = "HARNESS_FAILED"
    a[1] = row(a[1]["scenario_id"], "A", a[1]["repetition"], "NOT_RUN")
    floor = v.score(runs_of(full_dataset(A=a)), CLASSES)["decision_floor"]
    assert floor["per_arm"]["A"]["scored_ordinary_runs"] == 10
    assert floor["arms_short"] == ["A"]


def test_arm_b_is_held_to_the_ordinary_floor_but_not_the_fallback_rule() -> None:
    rows = [r for r in full_dataset() if not (r["arm"] == "B" and r["scenario_id"] in FALLBACK)]
    floor = v.score(runs_of(rows), CLASSES)["decision_floor"]
    assert floor["per_arm"]["B"]["fallback_rule_met"] is None
    assert floor["arms_short"] == []
    short = [r for r in full_dataset() if not (r["arm"] == "B" and r["scenario_id"] == ORDINARY[0])]
    floor = v.score(runs_of(short), CLASSES)["decision_floor"]
    assert floor["arms_short"] == ["B"]


def test_decision_insufficient_when_fallback_rule_unmet_for_an_arm() -> None:
    rows = [r for r in full_dataset() if not (r["arm"] == "E" and r["scenario_id"] in FALLBACK)]
    report = v.score(runs_of(rows), CLASSES)
    floor = report["decision_floor"]
    assert floor["per_arm"]["E"]["fallback_rule_met"] is False
    assert floor["arms_short"] == ["E"]
    assert report["decision"] == v.INSUFFICIENT
    assert report["conditional_edges"] == []


def test_arm_f_does_not_affect_the_decision_floor() -> None:
    rows = full_dataset(F=arm_rows("F", ALL_IDS, fail_all))
    report = v.score(runs_of(rows), CLASSES)
    assert set(report["decision_floor"]["per_arm"]) == set("ABCDE")
    assert report["decision_floor"]["arms_short"] == []


def test_floor_met_with_flat_data_keeps_current_policy() -> None:
    report = v.score(runs_of(full_dataset()), CLASSES)
    assert report["decision"] == v.DECISION_KEEP
    assert report["base_decision"] == v.DECISION_KEEP
    assert report["conditional_edges"] == []
    assert report["decision_rule"] == "predictions-v1 amendment 2"
    assert "decision_basis" not in report


def test_mapping_a_all_insufficient_or_floor_unmet() -> None:
    assert v.base_decision(statuses(), floor_met=True) == v.INSUFFICIENT
    assert v.base_decision(statuses(h3=v.SUPPORTED), floor_met=False) == v.INSUFFICIENT


def test_mapping_b_h3_falsified_h1_not_falsified() -> None:
    for h1 in (v.SUPPORTED, v.INSUFFICIENT):
        assert (
            v.base_decision(statuses(h1=h1, h3=v.FALSIFIED), floor_met=True)
            == v.DECISION_ORIGINAL_ROUTING
        )


def test_mapping_c_h3_and_h1_falsified() -> None:
    result = v.base_decision(statuses(h1=v.FALSIFIED, h3=v.FALSIFIED), floor_met=True)
    assert result == v.DECISION_HETEROGENEOUS


def test_mapping_d_h3_and_h1_supported() -> None:
    result = v.base_decision(statuses(h1=v.SUPPORTED, h3=v.SUPPORTED), floor_met=True)
    assert result == v.DECISION_SOL_WITH_LUNA


def test_mapping_e_h3_supported_alone() -> None:
    for h1 in (v.FALSIFIED, v.INSUFFICIENT):
        assert (
            v.base_decision(statuses(h1=h1, h3=v.SUPPORTED), floor_met=True)
            == v.DECISION_SOL_FANOUT
        )


def test_mapping_f_otherwise_keeps_current_policy() -> None:
    assert v.base_decision(statuses(h1=v.SUPPORTED), floor_met=True) == v.DECISION_KEEP
    assert v.base_decision(statuses(h2=v.FALSIFIED), floor_met=True) == v.DECISION_KEEP


def decide_with(h: dict[str, str], *, superseded: bool = False) -> dict[str, object]:
    runs = runs_of(full_dataset())
    return v.decide(runs, sorted(FALLBACK), h, superseded=superseded)


def test_conditional_wrap_for_h2_alone() -> None:
    out = decide_with(statuses(h1=v.SUPPORTED, h3=v.SUPPORTED, h2=v.SUPPORTED_FOR_FALLBACK))
    assert out["decision"] == v.DECISION_CONDITIONAL
    assert out["base_decision"] == v.DECISION_SOL_WITH_LUNA
    assert out["conditional_edges"] == [v.EDGE_TERRA]


def test_conditional_wrap_for_h4_alone() -> None:
    out = decide_with(statuses(h3=v.SUPPORTED, h4=v.SUPPORTED_FOR_FALLBACK))
    assert out["decision"] == v.DECISION_CONDITIONAL
    assert out["base_decision"] == v.DECISION_SOL_FANOUT
    assert out["conditional_edges"] == [v.EDGE_SOL_SINGLE]


def test_conditional_wrap_for_both_names_both_edges() -> None:
    both = statuses(h2=v.SUPPORTED_FOR_FALLBACK, h4=v.SUPPORTED_FOR_FALLBACK)
    out = decide_with(both)
    assert out["base_decision"] == v.DECISION_KEEP
    assert out["decision"] == v.DECISION_CONDITIONAL
    assert out["conditional_edges"] == [
        "Terra high for fallback_reasoning",
        "single-agent Sol for fallback_reasoning",
    ]


def test_no_conditional_wrap_on_insufficient_evidence() -> None:
    only_h2 = statuses(h2=v.SUPPORTED_FOR_FALLBACK)
    out = decide_with(only_h2, superseded=True)
    assert out["decision"] == v.INSUFFICIENT
    assert out["conditional_edges"] == []
    unmet = v.decide(runs_of(arm_rows("A", ALL_IDS)), sorted(FALLBACK), only_h2, superseded=False)
    assert unmet["decision"] == v.INSUFFICIENT


def test_report_lists_interpretations_with_lines() -> None:
    report = v.score(runs_of(full_dataset()), CLASSES)
    items = report["interpretations"]
    assert items and all(i["predictions_lines"] and i["reading"] for i in items)


def test_superseded_inputs_force_insufficient_everywhere() -> None:
    report = v.score(runs_of(full_dataset()), CLASSES, superseded=True)
    assert all(h["status"] == v.INSUFFICIENT for h in report["hypotheses"].values())
    assert report["decision"] == v.INSUFFICIENT


# ------------------------------------------------------------------------- parsing


def test_not_run_rows_are_counted_and_excluded() -> None:
    rows = [row(ORDINARY[0], "A", 1), row(ORDINARY[0], "A", 2, "NOT_RUN")]
    cell = v.cell_for(runs_of(rows), "A", v.CLASS_ORDINARY)
    assert (cell.not_run, cell.attempted, cell.eligible) == (1, 1, 1)


def test_class_comes_from_scenario_mapping_not_outcomes() -> None:
    run = runs_of([row(FALLBACK[0], "A", 1, "ACCEPTED")])[0]
    assert run.klass == v.CLASS_FALLBACK


def test_contract_violation_counts_as_non_accepted_scored_run() -> None:
    cell = v.cell_for(runs_of([row(ORDINARY[0], "A", 1, "CONTRACT_VIOLATION")]), "A", None)
    assert (cell.eligible, cell.accepted, cell.contract_violation) == (1, 0, 1)


def test_residual_defect_is_one_when_validation_fails_without_itemized_cause() -> None:
    assert runs_of([row(ORDINARY[0], "A", 1, "TASK_FAILED")])[0].residual == 1


def test_residual_defect_counts_scope_violations() -> None:
    assert runs_of([row(ORDINARY[0], "A", 1, "TASK_FAILED", scope=3)])[0].residual == 3


def test_wall_clock_uses_window_span_not_sum_of_invocations() -> None:
    item = row(ORDINARY[0], "A", 1)
    item["invocations"] = [
        {"window": {"start": 0, "end": 60}, "input_tokens": 1, "output_tokens": 1},
        {"window": {"start": 10, "end": 70}, "input_tokens": 1, "output_tokens": 1},
    ]
    assert runs_of([item])[0].seconds == 70


def test_uncached_tokens_are_input_plus_output_per_invocation() -> None:
    item = row(ORDINARY[0], "A", 1)
    item["invocations"] = [
        {"window": {"start": 0, "end": 1}, "input_tokens": 1000, "output_tokens": 50},
        {"window": {"start": 1, "end": 2}, "input_tokens": 200, "output_tokens": 5},
    ]
    assert runs_of([item])[0].tokens == 1255


def test_parse_rejects_unknown_scenario() -> None:
    with pytest.raises(v.VerdictInputError, match="not in the corpus"):
        runs_of([row("RB-99", "A", 1)])


def test_parse_rejects_unknown_status() -> None:
    with pytest.raises(v.VerdictInputError, match="unknown status"):
        runs_of([row(ORDINARY[0], "A", 1, "WEIRD")])


def test_parse_rejects_missing_repetition() -> None:
    item = row(ORDINARY[0], "A", 1)
    del item["repetition"]
    with pytest.raises(v.VerdictInputError, match="repetition"):
        runs_of([item])


@pytest.mark.parametrize("repetition", [0, 4, 12, -1])
def test_parse_rejects_repetition_outside_registered_design(repetition: int) -> None:
    with pytest.raises(v.VerdictInputError, match="registered design"):
        runs_of([row(ORDINARY[0], "A", repetition)])


def test_extra_repetitions_cannot_fill_the_decision_floor() -> None:
    extra = [row(ORDINARY[0], arm, rep) for arm in "ABCDE" for rep in range(1, 13)]
    with pytest.raises(v.VerdictInputError, match="registered design"):
        runs_of(extra)


@pytest.mark.parametrize(
    "windows",
    [[{}], [{"start": 0}], [{"end": 5}], [{"start": 0, "end": 5}, {}], [{"start": None, "end": 5}]],
)
def test_wall_clock_is_unknown_for_a_window_missing_start_or_end(
    windows: list[dict[str, Any]],
) -> None:
    item = row(ORDINARY[0], "A", 1)
    item["invocations"] = [
        {"window": window, "input_tokens": 1, "output_tokens": 1} for window in windows
    ]
    assert runs_of([item])[0].seconds is None


def test_parse_rejects_duplicate_key() -> None:
    with pytest.raises(v.VerdictInputError, match="duplicate"):
        runs_of([row(ORDINARY[0], "A", 1), row(ORDINARY[0], "A", 1)])


def test_parse_rejects_a_harness_that_is_neither_codex_nor_claude() -> None:
    with pytest.raises(v.VerdictInputError, match="not scorable"):
        runs_of([row(ORDINARY[0], "A", 1, harness="copilot")])
