"""Deterministic H1 to H4 scorer for the #5426 routing comparison.

Applies `evals/routing-benchmark/PREDICTIONS.md` (`predictions-v1` plus
Amendments 1, 2, and 3) to routing-benchmark result rows. Pure functions, no model
judgment, no I/O. The CLI is `eval_routing_verdicts.py`.

This module was written before any post-amendment result existed so that no
rule can be tuned after seeing data. Where the prose of PREDICTIONS.md leaves a
reading open, the reading taken is listed in `INTERPRETATIONS` with the line it
reads, and every report carries that list.

Canonical sources:

* Row shape: `result_to_dict` in `_routing_result.py` (live rows add
  `repetition`; a budget-cut row is `{"status": "NOT_RUN", ...}` from
  `eval_routing_benchmark._not_run`).
* Task class: `difficulty` in each `scenario.json`, passed in as `classes`. It
  is never derived from outcomes.
* Status values: `RunStatus` in `_routing_result.py` plus `NOT_RUN`.

Stricter than canonical: `parse_runs` rejects a duplicate
(scenario, arm, repetition) key within a harness, a harness that is neither Codex
nor Claude, and rows from more than one harness in one verdict. Amendment 3 scores
each harness under its own verdict and never pools them; `score_by_harness` is the
only entry that sees more than one, and it scores each alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from _routing_verdict_constants import (
    ACCEPTED,
    CLASS_FALLBACK,
    CLASS_ORDINARY,
    CODEX,
    COMPARED_ARMS,
    CONTRACT_VIOLATION,
    DECISION_CONDITIONAL,
    DECISION_HETEROGENEOUS,
    DECISION_KEEP,
    DECISION_ORDINARY_SCORED_FLOOR,
    DECISION_ORIGINAL_ROUTING,
    DECISION_RULE,
    DECISION_RULE_BY_HARNESS,
    DECISION_SOL_FANOUT,
    DECISION_SOL_WITH_LUNA,
    DEFECT_MARGIN,
    ECONOMICS_FACTOR,
    EDGE_SOL_SINGLE,
    EDGE_TERRA,
    EVIDENCE_FLOOR,
    FALLBACK_COMPARED_ARMS,
    FALLBACK_MIN_REPS,
    FALSIFIED,
    HARNESS_FAILED,
    HARNESS_FAILURE_LIMIT,
    INSUFFICIENT,
    INTERPRETATIONS,
    KNOWN_STATUSES,
    NOT_RUN,
    POOLED,
    PREDICTIONS_VERSION,
    QUALITY_MARGIN,
    REPETITIONS,
    ROLE_MODELS,
    SUPERSEDED_DIR,
    SUPPORTED,
    SUPPORTED_FOR_FALLBACK,
)
from _routing_verdict_tables import (
    Cell,
    Econ,
    Run,
    VerdictInputError,
    build_cell,
    cell_for,
    cell_summary,
    cell_table,
    economics_unmeasured,
    gate_reason,
    materially_better,
    non_inferior,
    parse_runs,
    partition_rows,
    rate_gap_at_least_sixth,
    rate_gap_under_sixth,
)

__all__ = [
    "verdict",
    "ACCEPTED",
    "CLASS_FALLBACK",
    "CLASS_ORDINARY",
    "CODEX",
    "COMPARED_ARMS",
    "CONTRACT_VIOLATION",
    "Cell",
    "DECISION_CONDITIONAL",
    "DECISION_HETEROGENEOUS",
    "DECISION_KEEP",
    "DECISION_ORDINARY_SCORED_FLOOR",
    "DECISION_ORIGINAL_ROUTING",
    "DECISION_RULE",
    "DECISION_SOL_FANOUT",
    "DECISION_SOL_WITH_LUNA",
    "DEFECT_MARGIN",
    "ECONOMICS_FACTOR",
    "EDGE_SOL_SINGLE",
    "EDGE_TERRA",
    "EVIDENCE_FLOOR",
    "Econ",
    "FALLBACK_COMPARED_ARMS",
    "FALLBACK_MIN_REPS",
    "FALSIFIED",
    "HARNESS_FAILED",
    "HARNESS_FAILURE_LIMIT",
    "INSUFFICIENT",
    "INTERPRETATIONS",
    "KNOWN_STATUSES",
    "NOT_RUN",
    "POOLED",
    "PREDICTIONS_VERSION",
    "QUALITY_MARGIN",
    "REPETITIONS",
    "Run",
    "SUPERSEDED_DIR",
    "SUPPORTED",
    "SUPPORTED_FOR_FALLBACK",
    "VerdictInputError",
    "base_decision",
    "build_cell",
    "cell_for",
    "cell_summary",
    "cell_table",
    "conditional_edges",
    "decide",
    "economics_unmeasured",
    "evaluate_h1",
    "evaluate_h2",
    "evaluate_h3",
    "evaluate_h4",
    "fallback_advantage",
    "fallback_no_advantage",
    "fallback_rule_met",
    "gate_reason",
    "materially_better",
    "non_inferior",
    "parse_runs",
    "partition_rows",
    "rate_gap_at_least_sixth",
    "rate_gap_under_sixth",
    "rep_directions",
    "score",
    "score_by_harness",
]


# ------------------------------------------------------------------- fallback rule


def rep_directions(
    runs: Sequence[Run], x_arm: str, c_arm: str, scenarios: Sequence[str]
) -> dict[str, list[int | None]]:
    """Per fallback scenario, per repetition: accepted(x) - accepted(c), or None."""
    index = {(r.arm, r.scenario_id, r.repetition): r for r in runs if r.eligible}
    directions: dict[str, list[int | None]] = {}
    for scenario in scenarios:
        row: list[int | None] = []
        for rep in REPETITIONS:
            x, c = index.get((x_arm, scenario, rep)), index.get((c_arm, scenario, rep))
            row.append(None if x is None or c is None else int(x.accepted) - int(c.accepted))
        directions[scenario] = row
    return directions


def _consistent(directions: Mapping[str, Sequence[int | None]], *, advantage: bool) -> bool:
    """I5: at least 2 of 3 repetitions agree in every fallback scenario."""
    if not directions:
        return False
    for values in directions.values():
        hits = sum(1 for d in values if d is not None and (d > 0 if advantage else d <= 0))
        if hits < FALLBACK_MIN_REPS:
            return False
    return True


def fallback_advantage(runs: Sequence[Run], x: Cell, c: Cell, scenarios: Sequence[str]) -> bool:
    directions = rep_directions(runs, x.arm, c.arm, scenarios)
    return rate_gap_at_least_sixth(x, c) and _consistent(directions, advantage=True)


def fallback_no_advantage(runs: Sequence[Run], x: Cell, c: Cell, scenarios: Sequence[str]) -> bool:
    directions = rep_directions(runs, x.arm, c.arm, scenarios)
    return rate_gap_under_sixth(x, c) and _consistent(directions, advantage=False)


def fallback_rule_met(runs: Sequence[Run], arm: str, scenarios: Sequence[str]) -> bool:
    """I9: enough usable runs in each fallback scenario to apply the waiver."""
    cell = cell_for(runs, arm, CLASS_FALLBACK)
    if gate_reason([cell], floor=False) is not None:
        return False
    for scenario in scenarios:
        usable = sum(1 for r in runs if r.arm == arm and r.scenario_id == scenario and r.eligible)
        if usable < FALLBACK_MIN_REPS:
            return False
    return bool(scenarios)


# ------------------------------------------------------------------------ hypotheses


def evaluate_h1(runs: Sequence[Run]) -> dict[str, Any]:
    c, a = cell_for(runs, "C", CLASS_ORDINARY), cell_for(runs, "A", CLASS_ORDINARY)
    detail = cell_summary(c, a)
    reason = gate_reason([c, a], floor=True) or economics_unmeasured([c, a])
    if reason:
        return verdict(INSUFFICIENT, reason, cells=detail)
    if non_inferior(c, a) and materially_better(c, a):
        return verdict(SUPPORTED, "C non-inferior to A and materially better", cells=detail)
    if non_inferior(a, c) and materially_better(a, c):
        return verdict(FALSIFIED, "A non-inferior to C and materially better", cells=detail)
    return verdict(INSUFFICIENT, "neither arm is non-inferior and materially better", cells=detail)


def _h2_ordinary(runs: Sequence[Run]) -> tuple[str | None, dict[str, Any]]:
    """Reason ordinary cannot clear D, or None when it shows no such advantage."""
    d, a, c = (cell_for(runs, arm, CLASS_ORDINARY) for arm in ("D", "A", "C"))
    detail = cell_summary(d, a, c)
    reason = gate_reason([d, a, c], floor=True)
    if reason:
        return f"ordinary class: {reason}", detail
    if rate_gap_at_least_sixth(d, a) and rate_gap_at_least_sixth(d, c):
        return "ordinary class shows the same advantage for D", detail
    return None, detail


def evaluate_h2(runs: Sequence[Run], fallback: Sequence[str]) -> dict[str, Any]:
    d, a, c = (cell_for(runs, arm, CLASS_FALLBACK) for arm in ("D", "A", "C"))
    reason = gate_reason([d, a, c], floor=False)
    ordinary_reason, ordinary_detail = _h2_ordinary(runs)
    detail = {"fallback": cell_summary(d, a, c), "ordinary": ordinary_detail}
    if reason:
        return verdict(INSUFFICIENT, f"fallback class: {reason}", cells=detail)
    if fallback_advantage(runs, d, a, fallback) and fallback_advantage(runs, d, c, fallback):
        if ordinary_reason:
            return verdict(INSUFFICIENT, ordinary_reason, cells=detail)
        return verdict(SUPPORTED_FOR_FALLBACK, "D beats A and C on fallback", cells=detail)
    if fallback_no_advantage(runs, d, a, fallback) and fallback_no_advantage(runs, d, c, fallback):
        return verdict(FALSIFIED, "no D advantage over A or C on fallback", cells=detail)
    return verdict(INSUFFICIENT, "fallback evidence rule not met either way", cells=detail)


def _h3_coverage_gap(runs: Sequence[Run], scenarios: Sequence[str]) -> str | None:
    """I12: H3 pools all six scenarios, so each arm needs a scored run in every one."""
    for arm in ("A", "B"):
        covered = {r.scenario_id for r in runs if r.arm == arm and r.eligible}
        missing = [sid for sid in scenarios if sid not in covered]
        if missing:
            names = ", ".join(missing)
            return f"arm {arm} has no scored run in {names}, so H3 is not pooled over all six"
    return None


def evaluate_h3(runs: Sequence[Run], scenarios: Sequence[str]) -> dict[str, Any]:
    a, b = cell_for(runs, "A", None), cell_for(runs, "B", None)
    detail = cell_summary(a, b)
    reason = (
        gate_reason([a, b], floor=True)
        or _h3_coverage_gap(runs, scenarios)
        or economics_unmeasured([a, b])
    )
    if reason:
        return verdict(INSUFFICIENT, reason, cells=detail)
    if non_inferior(a, b) and materially_better(a, b):
        return verdict(SUPPORTED, "A non-inferior to B pooled and materially better", cells=detail)
    if rate_gap_at_least_sixth(b, a) and not materially_better(a, b):
        return verdict(FALSIFIED, "B leads by >= 1/6 and the gap survives economics", cells=detail)
    return verdict(INSUFFICIENT, "neither SUPPORTED nor FALSIFIED rule holds", cells=detail)


def evaluate_h4(runs: Sequence[Run], fallback: Sequence[str]) -> dict[str, Any]:
    e, a = cell_for(runs, "E", CLASS_FALLBACK), cell_for(runs, "A", CLASS_FALLBACK)
    detail = cell_summary(e, a)
    reason = gate_reason([e, a], floor=False)
    if reason:
        return verdict(INSUFFICIENT, reason, cells=detail)
    if fallback_advantage(runs, e, a, fallback):
        return verdict(SUPPORTED_FOR_FALLBACK, "E beats A on fallback", cells=detail)
    unmeasured = economics_unmeasured([e, a])
    falsified = (
        not unmeasured
        and non_inferior(a, e)
        and materially_better(a, e)
        and _consistent(rep_directions(runs, "E", "A", fallback), advantage=False)
    )
    if falsified:
        return verdict(FALSIFIED, "A non-inferior to E and materially better", cells=detail)
    return verdict(INSUFFICIENT, unmeasured or "fallback evidence rule not met", cells=detail)


# -------------------------------------------------------------------------- decision


def _arm_floor(runs: Sequence[Run], arm: str, fallback: Sequence[str]) -> dict[str, Any]:
    ordinary = [r for r in runs if r.arm == arm and r.klass == CLASS_ORDINARY]
    scored = sum(1 for r in ordinary if r.eligible)
    on_fallback = arm in FALLBACK_COMPARED_ARMS
    rule = fallback_rule_met(runs, arm, fallback) if on_fallback else None
    return {
        "scored_ordinary_runs": scored,
        "scored_ordinary_required": DECISION_ORDINARY_SCORED_FLOOR,
        "accepted_ordinary_runs": sum(1 for r in ordinary if r.accepted),
        "fallback_rule_met": rule,
        "meets_floor": scored >= DECISION_ORDINARY_SCORED_FLOOR and rule is not False,
    }


def verdict(status: str, reason: str, **detail: object) -> dict[str, Any]:
    return {"status": status, "reason": reason, **detail}


def base_decision(statuses: Mapping[str, str], *, floor_met: bool) -> str:
    """Amendment 2 item 2, first match wins."""
    h1, h3 = statuses["H1"], statuses["H3"]
    value: str = DECISION_KEEP
    if not floor_met or all(status == INSUFFICIENT for status in statuses.values()):
        value = INSUFFICIENT
    elif h3 == FALSIFIED:
        value = DECISION_HETEROGENEOUS if h1 == FALSIFIED else DECISION_ORIGINAL_ROUTING
    elif h3 == SUPPORTED:
        value = DECISION_SOL_WITH_LUNA if h1 == SUPPORTED else DECISION_SOL_FANOUT
    return value


def conditional_edges(statuses: Mapping[str, str]) -> list[str]:
    edges = []
    if statuses["H2"] == SUPPORTED_FOR_FALLBACK:
        edges.append(EDGE_TERRA)
    if statuses["H4"] == SUPPORTED_FOR_FALLBACK:
        edges.append(EDGE_SOL_SINGLE)
    return edges


def decide(
    runs: Sequence[Run],
    fallback: Sequence[str],
    statuses: Mapping[str, str],
    *,
    superseded: bool,
    rule: str = DECISION_RULE,
) -> dict[str, Any]:
    """Decision floor (Amendment 2 item 1) and mapping (item 2); no judgment.

    Amendment 3 keeps both unchanged for Claude, so `rule` only names which amendment
    the harness is scored under.
    """
    per_arm = {arm: _arm_floor(runs, arm, fallback) for arm in COMPARED_ARMS}
    short = [arm for arm, item in per_arm.items() if not item["meets_floor"]]
    floor = {"per_arm": per_arm, "arms_short": short, "pre_amendment_inputs": superseded}
    base = base_decision(statuses, floor_met=not (superseded or short))
    edges = [] if base == INSUFFICIENT else conditional_edges(statuses)
    return {
        "decision": DECISION_CONDITIONAL if edges else base,
        "base_decision": base,
        "conditional_edges": edges,
        "decision_rule": rule,
        "decision_floor": floor,
    }


def _superseded_hypotheses() -> dict[str, dict[str, Any]]:
    reason = "pre-amendment runs do not count toward the evidence floor (Amendment 1)"
    return {name: verdict(INSUFFICIENT, reason) for name in ("H1", "H2", "H3", "H4")}


def _refuse_mixed_harnesses(runs: Sequence[Run], harness: str) -> None:
    foreign = sorted({run.harness for run in runs} - {harness})
    if foreign:
        raise VerdictInputError(
            f"cannot score {foreign} rows in the {harness!r} verdict: "
            "a verdict is per harness and harnesses are never pooled"
        )


def score(
    runs: Sequence[Run],
    classes: Mapping[str, str],
    *,
    superseded: bool = False,
    harness: str = CODEX,
) -> dict[str, Any]:
    """Full report for one harness: cell tables, H1 to H4 statuses, decision, interpretations.

    Raises `VerdictInputError` when `runs` holds a row of another harness.
    """
    _refuse_mixed_harnesses(runs, harness)
    fallback = sorted(sid for sid, klass in classes.items() if klass == CLASS_FALLBACK)
    arms = sorted({run.arm for run in runs})
    tables = [
        cell_table(cell_for(runs, arm, klass))
        for arm in arms
        for klass in sorted(set(classes.values()))
    ]
    tables += [cell_table(cell_for(runs, arm, None)) for arm in arms]
    if superseded:
        hypotheses = _superseded_hypotheses()
    else:
        hypotheses = {
            "H1": evaluate_h1(runs),
            "H2": evaluate_h2(runs, fallback),
            "H3": evaluate_h3(runs, sorted(classes)),
            "H4": evaluate_h4(runs, fallback),
        }
    return {
        "predictions_version": PREDICTIONS_VERSION,
        "harness": harness,
        "role_models": dict(ROLE_MODELS[harness]),
        "rows_scored": sum(1 for run in runs if run.status != NOT_RUN),
        "rows_not_run": sum(1 for run in runs if run.status == NOT_RUN),
        "tables": tables,
        "hypotheses": hypotheses,
        **decide(
            runs,
            fallback,
            {k: str(h["status"]) for k, h in hypotheses.items()},
            superseded=superseded,
            rule=DECISION_RULE_BY_HARNESS[harness],
        ),
        "interpretations": list(INTERPRETATIONS),
    }


def score_by_harness(
    runs_by_harness: Mapping[str, Sequence[Run]],
    classes: Mapping[str, str],
    *,
    superseded: bool = False,
) -> dict[str, Any]:
    """One report keyed by harness. Each harness is scored alone, never pooled (Amendment 3).

    Each block is the harness's own H1 to H4, decision, and floor. The interpretations are
    listed once at the top, because they are the same for every harness.
    """
    blocks: dict[str, dict[str, Any]] = {}
    for harness in sorted(runs_by_harness):
        report = score(runs_by_harness[harness], classes, superseded=superseded, harness=harness)
        del report["interpretations"]
        blocks[harness] = report
    return {
        "predictions_version": PREDICTIONS_VERSION,
        "pooled_across_harnesses": False,
        "harnesses": blocks,
        "interpretations": list(INTERPRETATIONS),
    }
