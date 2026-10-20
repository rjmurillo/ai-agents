"""Tests for the #5426 routing verdict scorer (`_routing_verdicts.py`, CLI).

Synthetic rows cover every verdict branch of H1 to H4, the evidence floor, the
fallback waiver, the harness-failure limit, undefined economics, the
Amendment 1 pooling refusal, and CLI exit codes. One test runs the scorer on
the real `results-2026-10-03` files. Rows mirror `result_to_dict` in
`_routing_result.py`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _routing_verdicts as v  # noqa: E402
import eval_routing_verdicts as cli  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
REAL_RESULTS = REPO / "evals" / "routing-benchmark" / "results-2026-10-03"

ORDINARY = (
    "RB-01-bounded-implementation",
    "RB-04-scope-expansion",
    "RB-05-plausible-but-wrong",
    "RB-06-architecture-resolved",
)
FALLBACK = ("RB-02-multi-file-invariants", "RB-03-investigate-before-edit")
CLASSES = {**dict.fromkeys(ORDINARY, v.CLASS_ORDINARY), **dict.fromkeys(FALLBACK, v.CLASS_FALLBACK)}
ALL_IDS = ORDINARY + FALLBACK

Policy = Callable[[str, int], str]


def accept_all(_sid: str, _rep: int) -> str:
    return "ACCEPTED"


def fail_all(_sid: str, _rep: int) -> str:
    return "TASK_FAILED"


def row(
    sid: str,
    arm: str,
    rep: int,
    status: str = "ACCEPTED",
    *,
    seconds: float = 100.0,
    tokens: int = 1000,
    scope: int = 0,
    harness: str = "codex",
) -> dict[str, Any]:
    if status == "NOT_RUN":
        return {
            "status": status,
            "scenario_id": sid,
            "arm": arm,
            "harness": harness,
            "repetition": rep,
            "reason": "invocation budget spent",
        }
    verdict = "PASS" if status == "ACCEPTED" else "FAIL"
    return {
        "scenario_id": sid,
        "arm": arm,
        "harness": {"name": harness, "version": "codex-cli 0.160.0"},
        "status": status,
        "repetition": rep,
        "invocations": [
            {
                "window": {"start": 0.0, "end": seconds},
                "input_tokens": tokens - 100,
                "output_tokens": 100,
            }
        ],
        "validation": {
            "verdict": verdict,
            "scope_violations": [f"x{i}" for i in range(scope)],
            "missing_expected": [],
        },
    }


def arm_rows(
    arm: str,
    ids: tuple[str, ...],
    policy: Policy = accept_all,
    *,
    seconds: float = 100.0,
    tokens: int = 1000,
    scope: int = 0,
) -> list[dict[str, Any]]:
    return [
        row(sid, arm, rep, policy(sid, rep), seconds=seconds, tokens=tokens, scope=scope)
        for sid in ids
        for rep in (1, 2, 3)
    ]


def accept_first(count: int) -> Policy:
    """Accept the first `count` (scenario, rep) cells in iteration order."""
    order: dict[tuple[str, int], int] = {}

    def policy(sid: str, rep: int) -> str:
        index = order.setdefault((sid, rep), len(order))
        return "ACCEPTED" if index < count else "TASK_FAILED"

    return policy


def runs_of(*groups: list[dict[str, Any]]) -> list[v.Run]:
    return v.parse_runs([r for g in groups for r in g], CLASSES)


def status_of(runs: list[v.Run], name: str) -> str:
    report = v.score(runs, CLASSES)
    return str(report["hypotheses"][name]["status"])  # type: ignore[index]


def full_dataset(**overrides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every arm accepts everything on every scenario unless `overrides[arm]` replaces it."""
    rows: list[dict[str, Any]] = []
    for arm in "ABCDEF":
        rows += overrides.get(arm) or arm_rows(arm, ALL_IDS)
    return rows


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
    h1 = report["hypotheses"]["H1"]  # type: ignore[index]
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
    h1 = report["hypotheses"]["H1"]  # type: ignore[index]
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
    table = next(t for t in report["tables"] if t["arm"] == "C" and t["class"] == v.CLASS_ORDINARY)  # type: ignore[attr-defined]
    assert table["mean_seconds_per_accepted"] is None
    assert table["mean_uncached_tokens_per_accepted"] is None
    assert status_of(runs, "H1") == v.INSUFFICIENT


def test_h1_unknown_tokens_make_economics_unmeasured() -> None:
    c = arm_rows("C", ORDINARY, seconds=50, tokens=500)
    c[0]["invocations"][0]["input_tokens"] = None
    report = v.score(runs_of(c, arm_rows("A", ORDINARY)), CLASSES)
    h1 = report["hypotheses"]["H1"]  # type: ignore[index]
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
    h2 = report["hypotheses"]["H2"]  # type: ignore[index]
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
    cells = report["hypotheses"]["H2"]["cells"]  # type: ignore[index]
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


# ------------------------------------------------------------------------- decision


def test_one_arm_short_forces_insufficient_even_when_total_is_at_least_twelve() -> None:
    rows = full_dataset(A=arm_rows("A", ALL_IDS, accept_first(11)))
    report = v.score(runs_of(rows), CLASSES)
    floor = report["decision_floor"]
    assert sum(a["accepted_ordinary_runs"] for a in floor["per_arm"].values()) >= 12  # type: ignore[index]
    assert floor["per_arm"]["A"]["accepted_ordinary_runs"] == 11  # type: ignore[index]
    assert floor["arms_short"] == ["A"]  # type: ignore[index]
    assert report["decision"] == v.INSUFFICIENT


def test_arm_b_is_held_to_the_ordinary_floor_but_not_the_fallback_rule() -> None:
    rows = [r for r in full_dataset() if not (r["arm"] == "B" and r["scenario_id"] in FALLBACK)]
    floor = v.score(runs_of(rows), CLASSES)["decision_floor"]
    assert floor["per_arm"]["B"]["fallback_rule_met"] is None  # type: ignore[index]
    assert floor["arms_short"] == []  # type: ignore[index]
    short = full_dataset(B=arm_rows("B", ALL_IDS, fail_all))
    floor = v.score(runs_of(short), CLASSES)["decision_floor"]
    assert floor["arms_short"] == ["B"]  # type: ignore[index]


def test_decision_insufficient_when_fallback_rule_unmet_for_an_arm() -> None:
    rows = [r for r in full_dataset() if not (r["arm"] == "E" and r["scenario_id"] in FALLBACK)]
    report = v.score(runs_of(rows), CLASSES)
    floor = report["decision_floor"]
    assert floor["per_arm"]["E"]["fallback_rule_met"] is False  # type: ignore[index]
    assert floor["per_arm"]["E"]["accepted_ordinary_runs"] == 12  # type: ignore[index]
    assert floor["arms_short"] == ["E"]  # type: ignore[index]
    assert report["decision"] == v.INSUFFICIENT


def test_arm_f_does_not_affect_the_decision_floor() -> None:
    rows = full_dataset(F=arm_rows("F", ALL_IDS, fail_all))
    report = v.score(runs_of(rows), CLASSES)
    assert set(report["decision_floor"]["per_arm"]) == set("ABCDE")  # type: ignore[index]
    assert report["decision"] is None


def test_decision_is_null_with_basis_when_floor_met() -> None:
    report = v.score(runs_of(full_dataset()), CLASSES)
    assert report["decision"] is None
    assert report["decision_basis"] == v.DECISION_NOT_REGISTERED
    assert report["decision_floor"]["arms_short"] == []  # type: ignore[index]
    assert set(report["hypotheses"]) == {"H1", "H2", "H3", "H4"}  # type: ignore[arg-type]


def test_report_lists_interpretations_with_lines() -> None:
    report = v.score(runs_of(full_dataset()), CLASSES)
    items = report["interpretations"]
    assert items and all(i["predictions_lines"] and i["reading"] for i in items)  # type: ignore[union-attr]


def test_superseded_inputs_force_insufficient_everywhere() -> None:
    report = v.score(runs_of(full_dataset()), CLASSES, superseded=True)
    assert all(h["status"] == v.INSUFFICIENT for h in report["hypotheses"].values())  # type: ignore[attr-defined]
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


def test_parse_rejects_duplicate_key() -> None:
    with pytest.raises(v.VerdictInputError, match="duplicate"):
        runs_of([row(ORDINARY[0], "A", 1), row(ORDINARY[0], "A", 1)])


def test_parse_rejects_non_codex_harness() -> None:
    with pytest.raises(v.VerdictInputError, match="not scorable"):
        runs_of([row(ORDINARY[0], "A", 1, harness="claude")])


# ----------------------------------------------------------------------------- CLI


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def run_cli(*args: str) -> int:
    return cli.main(list(args))


def test_cli_scores_and_writes_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    results = write_jsonl(tmp_path / "run" / "rows.jsonl", full_dataset())
    out = tmp_path / "report.json"
    assert run_cli("--results", str(results), "--output", str(out)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(out.read_text(encoding="utf-8"))
    assert printed["decision"] is None


def test_cli_accepts_several_result_files(tmp_path: Path) -> None:
    rows = full_dataset()
    first = write_jsonl(tmp_path / "a.jsonl", rows[:100])
    second = write_jsonl(tmp_path / "b.jsonl", rows[100:])
    assert run_cli("--results", str(first), str(second)) == 0


def test_cli_exit_2_without_arguments() -> None:
    assert run_cli() == 2


def test_cli_exit_2_on_missing_file(tmp_path: Path) -> None:
    assert run_cli("--results", str(tmp_path / "nope.jsonl")) == 2


def test_cli_exit_2_on_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{not json\n", encoding="utf-8")
    assert run_cli("--results", str(bad)) == 2


def test_cli_exit_2_on_non_object_row(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("[1]\n", encoding="utf-8")
    assert run_cli("--results", str(bad)) == 2


def test_cli_exit_2_on_unknown_scenario(tmp_path: Path) -> None:
    results = write_jsonl(tmp_path / "r.jsonl", [row("RB-99", "A", 1)])
    assert run_cli("--results", str(results)) == 2


def test_cli_exit_2_on_bad_corpus(tmp_path: Path) -> None:
    results = write_jsonl(tmp_path / "r.jsonl", full_dataset())
    assert run_cli("--results", str(results), "--corpus", str(tmp_path / "missing")) == 2


def test_cli_exit_1_when_every_row_is_not_run(tmp_path: Path) -> None:
    results = write_jsonl(tmp_path / "r.jsonl", [row(ORDINARY[0], "A", 1, "NOT_RUN")])
    assert run_cli("--results", str(results)) == 1


def test_cli_blank_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    path.write_text("\n" + json.dumps(row(ORDINARY[0], "A", 1)) + "\n\n", encoding="utf-8")
    assert run_cli("--results", str(path)) == 0


# ---------------------------------------------------------- Amendment 1 pooling guard


def test_pooling_guard_refuses_mixed_old_and_new(tmp_path: Path) -> None:
    old = write_jsonl(tmp_path / v.SUPERSEDED_DIR / "old.jsonl", [row(ORDINARY[0], "A", 1)])
    new = write_jsonl(tmp_path / "results-2026-11-01" / "new.jsonl", [row(ORDINARY[0], "A", 2)])
    with pytest.raises(v.VerdictInputError, match="Amendment 1"):
        cli.check_pooling([old, new])
    assert run_cli("--results", str(old), str(new)) == 2


def test_pooling_guard_allows_new_runs_only(tmp_path: Path) -> None:
    new = write_jsonl(tmp_path / "results-2026-11-01" / "new.jsonl", [row(ORDINARY[0], "A", 1)])
    assert cli.check_pooling([new]) is False


def test_superseded_alone_is_scored_but_every_verdict_is_insufficient(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    old = write_jsonl(tmp_path / v.SUPERSEDED_DIR / "old.jsonl", full_dataset())
    assert run_cli("--results", str(old)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert {h["status"] for h in printed["hypotheses"].values()} == {v.INSUFFICIENT}
    assert printed["decision"] == v.INSUFFICIENT
    assert printed["decision_floor"]["pre_amendment_inputs"] is True


def test_real_results_2026_10_03_are_insufficient_for_all_four(
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = sorted(REAL_RESULTS.glob("*.jsonl"))
    assert len(files) == 3
    assert run_cli("--results", *map(str, files)) == 0
    printed = json.loads(capsys.readouterr().out)
    assert {k: h["status"] for k, h in printed["hypotheses"].items()} == dict.fromkeys(
        ("H1", "H2", "H3", "H4"), v.INSUFFICIENT
    )
    assert printed["decision"] == v.INSUFFICIENT
    assert printed["rows_scored"] == 36
    assert printed["rows_not_run"] == 0


def test_real_results_cannot_pool_with_a_later_file(tmp_path: Path) -> None:
    later = write_jsonl(tmp_path / "later.jsonl", [row(ORDINARY[0], "A", 2)])
    first = next(iter(sorted(REAL_RESULTS.glob("*.jsonl"))))
    assert run_cli("--results", str(first), str(later)) == 2
