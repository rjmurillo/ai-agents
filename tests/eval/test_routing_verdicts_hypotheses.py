"""Tests for the H1 to H4 rules of the routing verdict scorer (issue #5426)."""

from __future__ import annotations

from typing import Any

from tests.eval._routing_verdicts_test_support import (
    ALL_IDS,
    CLASSES,
    FALLBACK,
    ORDINARY,
    Policy,
    accept_all,
    accept_first,
    arm_rows,
    fail_all,
    row,
    runs_of,
    status_of,
    v,
)

# ----------------------------------------------------------------------------- H1


def test_h1_supported_when_c_non_inferior_and_cheaper() -> None:
    runs = runs_of(
        arm_rows("C", ORDINARY, seconds=50, tokens=500),
        arm_rows("A", ORDINARY, seconds=100, tokens=1000),
    )
    assert status_of(runs, "H1") == v.SUPPORTED


def test_h1_falsified_when_a_non_inferior_and_cheaper() -> None:
    runs = runs_of(
        arm_rows("C", ORDINARY, seconds=100, tokens=1000),
        arm_rows("A", ORDINARY, seconds=50, tokens=500),
    )
    assert status_of(runs, "H1") == v.FALSIFIED


def test_h1_insufficient_when_economics_not_25_percent_lower() -> None:
    runs = runs_of(
        arm_rows("C", ORDINARY, seconds=80, tokens=500),
        arm_rows("A", ORDINARY, seconds=100, tokens=1000),
    )
    assert status_of(runs, "H1") == v.INSUFFICIENT


def test_h1_requires_both_latency_and_tokens() -> None:
    runs = runs_of(
        arm_rows("C", ORDINARY, seconds=50, tokens=1000),
        arm_rows("A", ORDINARY, seconds=100, tokens=1000),
    )
    assert status_of(runs, "H1") == v.INSUFFICIENT


def test_h1_exactly_25_percent_lower_counts() -> None:
    runs = runs_of(
        arm_rows("C", ORDINARY, seconds=75, tokens=750),
        arm_rows("A", ORDINARY, seconds=100, tokens=1000),
    )
    assert status_of(runs, "H1") == v.SUPPORTED


def test_h1_floor_unmet_below_eight_scored_runs() -> None:
    c = arm_rows("C", ORDINARY, seconds=50, tokens=500)[:7]
    runs = runs_of(c, arm_rows("A", ORDINARY))
    report = v.score(runs, CLASSES)
    h1 = report["hypotheses"]["H1"]
    assert h1["status"] == v.INSUFFICIENT
    assert "below the floor of 8" in h1["reason"]


def test_h1_floor_met_at_exactly_eight_scored_runs() -> None:
    c = arm_rows("C", ORDINARY, seconds=50, tokens=500)[:8]
    a = arm_rows("A", ORDINARY)[:8]
    assert status_of(runs_of(c, a), "H1") == v.SUPPORTED


def test_h1_cell_with_more_than_20_percent_harness_failures_is_insufficient() -> None:
    c = arm_rows("C", ORDINARY, seconds=50, tokens=500)
    for item in c[:3]:  # 3 of 12 = 25 percent
        item["status"] = "HARNESS_FAILED"
    report = v.score(runs_of(c, arm_rows("A", ORDINARY)), CLASSES)
    h1 = report["hypotheses"]["H1"]
    assert h1["status"] == v.INSUFFICIENT
    assert "harness failures" in h1["reason"]


def test_h1_harness_failures_at_exactly_20_percent_are_allowed() -> None:
    c = arm_rows("C", ORDINARY, seconds=50, tokens=500)[:10]
    for item in c[:2]:  # 2 of 10 = 20 percent, 8 scored
        item["status"] = "HARNESS_FAILED"
    a = arm_rows("A", ORDINARY)[:8]
    assert status_of(runs_of(c, a), "H1") == v.SUPPORTED


def test_h1_not_inferior_fails_when_acceptance_gap_exceeds_one_sixth() -> None:
    c = arm_rows("C", ORDINARY, accept_first(9), seconds=10, tokens=10)  # 9 of 12
    runs = runs_of(c, arm_rows("A", ORDINARY))
    assert status_of(runs, "H1") == v.INSUFFICIENT


def test_h1_non_inferior_at_exactly_one_sixth_gap() -> None:
    c = arm_rows("C", ORDINARY, accept_first(10), seconds=10, tokens=10)  # 10 of 12
    runs = runs_of(c, arm_rows("A", ORDINARY))
    assert status_of(runs, "H1") == v.SUPPORTED


def test_h1_residual_defects_above_half_per_run_break_non_inferiority() -> None:
    c = arm_rows("C", ORDINARY, seconds=10, tokens=10, scope=1)
    runs = runs_of(c, arm_rows("A", ORDINARY))
    assert status_of(runs, "H1") == v.INSUFFICIENT


def test_h1_zero_accepted_economics_is_undefined_never_better() -> None:
    runs = runs_of(arm_rows("C", ORDINARY, fail_all), arm_rows("A", ORDINARY, fail_all))
    report = v.score(runs, CLASSES)
    table = next(t for t in report["tables"] if t["arm"] == "C" and t["class"] == v.CLASS_ORDINARY)
    assert table["mean_seconds_per_accepted"] is None
    assert table["mean_uncached_tokens_per_accepted"] is None
    assert status_of(runs, "H1") == v.INSUFFICIENT


def test_h1_unknown_tokens_make_economics_unmeasured() -> None:
    c = arm_rows("C", ORDINARY, seconds=50, tokens=500)
    c[0]["invocations"][0]["input_tokens"] = None
    report = v.score(runs_of(c, arm_rows("A", ORDINARY)), CLASSES)
    h1 = report["hypotheses"]["H1"]
    assert h1["status"] == v.INSUFFICIENT
    assert "unknown time or tokens" in h1["reason"]


def test_per_accepted_divides_all_scored_runs_by_accepted_count() -> None:
    rows = [
        row(ORDINARY[0], "A", 1, "ACCEPTED", seconds=100),
        row(ORDINARY[0], "A", 2, "TASK_FAILED", seconds=300),
        row(ORDINARY[0], "A", 3, "HARNESS_FAILED", seconds=9999),
    ]
    cell = v.cell_for(runs_of(rows), "A", v.CLASS_ORDINARY)
    assert cell.econ.seconds == 400  # (100 + 300) / 1 accepted; the harness failure is excluded
    assert cell.harness_failed == 1
    assert cell.eligible == 2


# ----------------------------------------------------------------------------- H3


def test_h3_supported_pooled_all_six() -> None:
    runs = runs_of(
        arm_rows("A", ALL_IDS, seconds=50, tokens=500),
        arm_rows("B", ALL_IDS, seconds=100, tokens=1000),
    )
    assert status_of(runs, "H3") == v.SUPPORTED


def test_h3_falsified_when_b_leads_and_gap_survives_economics() -> None:
    runs = runs_of(
        arm_rows("A", ALL_IDS, accept_first(10), seconds=100, tokens=1000),
        arm_rows("B", ALL_IDS, seconds=100, tokens=1000),
    )
    assert status_of(runs, "H3") == v.FALSIFIED


def test_h3_insufficient_when_b_leads_but_a_is_materially_cheaper() -> None:
    runs = runs_of(
        arm_rows("A", ALL_IDS, accept_first(10), seconds=10, tokens=10),
        arm_rows("B", ALL_IDS, seconds=100, tokens=1000),
    )
    assert status_of(runs, "H3") == v.INSUFFICIENT


def test_h3_falsified_when_a_accepts_nothing() -> None:
    runs = runs_of(arm_rows("A", ALL_IDS, fail_all), arm_rows("B", ALL_IDS))
    assert status_of(runs, "H3") == v.FALSIFIED


def test_h3_insufficient_when_pooled_floor_unmet() -> None:
    runs = runs_of(arm_rows("A", ALL_IDS)[:7], arm_rows("B", ALL_IDS))
    assert status_of(runs, "H3") == v.INSUFFICIENT


def test_h3_insufficient_when_arm_missing() -> None:
    assert status_of(runs_of(arm_rows("A", ALL_IDS)), "H3") == v.INSUFFICIENT


# ----------------------------------------------------------------------------- H2


def only_rb02(count_rep: int) -> Policy:
    """Accept on RB-02 for `count_rep` reps and never on RB-03."""

    def policy(sid: str, rep: int) -> str:
        return "ACCEPTED" if sid == FALLBACK[0] and rep <= count_rep else "TASK_FAILED"

    return policy


def h2_runs(d_fallback: list[dict[str, Any]], d_ordinary: list[dict[str, Any]] | None = None):
    d_ord = d_ordinary if d_ordinary is not None else arm_rows("D", ORDINARY, accept_first(6))
    return runs_of(
        arm_rows("A", ORDINARY, accept_first(6)),
        arm_rows("C", ORDINARY, accept_first(6)),
        d_ord,
        arm_rows("A", FALLBACK, fail_all),
        arm_rows("C", FALLBACK, fail_all),
        d_fallback,
    )


def test_h2_supported_for_fallback_with_flat_ordinary() -> None:
    assert status_of(h2_runs(arm_rows("D", FALLBACK)), "H2") == v.SUPPORTED_FOR_FALLBACK


def test_h2_insufficient_when_advantage_on_one_fallback_scenario_only() -> None:
    d = arm_rows("D", FALLBACK, only_rb02(3))
    assert status_of(h2_runs(d), "H2") == v.INSUFFICIENT


def test_h2_insufficient_when_only_one_of_three_reps_agree() -> None:
    def policy(sid: str, rep: int) -> str:
        return "ACCEPTED" if rep == 1 else "TASK_FAILED"

    assert status_of(h2_runs(arm_rows("D", FALLBACK, policy)), "H2") == v.INSUFFICIENT


def test_h2_supported_with_two_of_three_reps_each() -> None:
    def policy(sid: str, rep: int) -> str:
        return "ACCEPTED" if rep <= 2 else "TASK_FAILED"

    assert status_of(h2_runs(arm_rows("D", FALLBACK, policy)), "H2") == v.SUPPORTED_FOR_FALLBACK


def test_h2_insufficient_when_ordinary_shows_the_same_advantage() -> None:
    d_ord = arm_rows("D", ORDINARY)
    report = v.score(h2_runs(arm_rows("D", FALLBACK), d_ord), CLASSES)
    h2 = report["hypotheses"]["H2"]
    assert h2["status"] == v.INSUFFICIENT
    assert "ordinary" in h2["reason"]


def test_h2_insufficient_when_ordinary_below_floor() -> None:
    d_ord = arm_rows("D", ORDINARY, accept_first(6))[:7]
    assert status_of(h2_runs(arm_rows("D", FALLBACK), d_ord), "H2") == v.INSUFFICIENT


def test_h2_falsified_when_no_advantage_over_either_comparator() -> None:
    runs = runs_of(
        arm_rows("A", FALLBACK),
        arm_rows("C", FALLBACK),
        arm_rows("D", FALLBACK),
    )
    assert status_of(runs, "H2") == v.FALSIFIED


def test_h2_insufficient_when_advantage_over_a_but_not_over_c() -> None:
    runs = runs_of(
        arm_rows("A", FALLBACK, fail_all),
        arm_rows("C", FALLBACK),
        arm_rows("D", FALLBACK),
    )
    assert status_of(runs, "H2") == v.INSUFFICIENT


def test_h2_harness_failures_in_fallback_cell_are_insufficient() -> None:
    d = arm_rows("D", FALLBACK)
    d[0]["status"] = d[1]["status"] = "HARNESS_FAILED"  # 2 of 6 = 33 percent
    assert status_of(h2_runs(d), "H2") == v.INSUFFICIENT


def test_h2_reports_ordinary_and_fallback_separately() -> None:
    report = v.score(h2_runs(arm_rows("D", FALLBACK)), CLASSES)
    cells = report["hypotheses"]["H2"]["cells"]
    assert set(cells) == {"fallback", "ordinary"}


# ----------------------------------------------------------------------------- H4


def h4_runs(e_policy: Policy, a_policy: Policy = fail_all, **econ: Any):
    return runs_of(
        arm_rows("E", FALLBACK, e_policy, **econ.get("e", {})),
        arm_rows("A", FALLBACK, a_policy, **econ.get("a", {})),
    )


def test_h4_supported_for_fallback() -> None:
    assert status_of(h4_runs(accept_all), "H4") == v.SUPPORTED_FOR_FALLBACK


def test_h4_waiver_unmet_when_advantage_on_one_scenario_only() -> None:
    assert status_of(h4_runs(only_rb02(3)), "H4") == v.INSUFFICIENT


def test_h4_falsified_when_a_is_non_inferior_and_cheaper() -> None:
    runs = h4_runs(
        accept_all,
        accept_all,
        e={"seconds": 100, "tokens": 1000},
        a={"seconds": 50, "tokens": 500},
    )
    assert status_of(runs, "H4") == v.FALSIFIED


def test_h4_insufficient_when_equal_quality_and_equal_economics() -> None:
    assert status_of(h4_runs(accept_all, accept_all), "H4") == v.INSUFFICIENT


def test_h4_insufficient_when_a_fails_everything_and_e_does_too() -> None:
    assert status_of(h4_runs(fail_all, fail_all), "H4") == v.INSUFFICIENT


def test_h4_insufficient_with_missing_arm() -> None:
    assert status_of(runs_of(arm_rows("E", FALLBACK)), "H4") == v.INSUFFICIENT
