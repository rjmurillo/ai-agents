"""Aggregation and verdicts for the longitudinal pilot (issue #6993).

Split from `_longitudinal_pilot.py`. Reads cell records, never raw answers.
The `vendor_only` baseline is always listed first. Costs and minutes that no
one measured stay `None`; a total is `None` while any component is unknown.
"""

from __future__ import annotations

from typing import Any

from _longitudinal_pilot import BASELINE, CONDITIONS, LIMITATIONS, Ledger, stale_truth


def _sum_known(values: list[float | None]) -> tuple[float | None, int]:
    known = [v for v in values if v is not None]
    return (round(sum(known), 6) if known else None), len(values) - len(known)


def _condition_summary(
    recs: list[dict[str, Any]], tasks: dict[str, dict[str, Any]], bootstrap_usd: float | None
) -> dict[str, Any]:
    graded = [r for r in recs if not r.get("skipped") and not r.get("is_error")]
    accepted = {(r["task_id"], r["repeat"]) for r in graded if r["accepted"]}
    done = {(r["task_id"], r["repeat"]) for r in graded}
    pairs = [
        ((t["followup_of"], r["repeat"]), (t["id"], r["repeat"]))
        for r in graded
        for t in [tasks[r["task_id"]]]
        if t.get("followup_of") and (t["followup_of"], r["repeat"]) in done
    ]
    minutes, unknown_minutes = _sum_known([r["human_minutes"] for r in graded])
    exec_ok, exec_unknown = _sum_known([r["cost_usd"] for r in graded if r["accepted"]])
    rework, rework_unknown = _sum_known([r["cost_usd"] for r in graded if not r["accepted"]])
    cost: dict[str, float | None] = {
        "bootstrap_usd": bootstrap_usd,
        "execution_usd": exec_ok,
        "retrieval_usd": None,
        "maintenance_usd": 0.0,
        "rework_usd": rework,
    }
    unknown = sorted(k for k, v in cost.items() if v is None)
    if exec_unknown or rework_unknown:
        unknown.append("execution_or_rework_cells_without_cost")
    known_total, _ = _sum_known(list(cost.values()))
    return {
        "cells": len(recs),
        "skipped": sum(1 for r in recs if r.get("skipped")),
        "errors": sum(1 for r in recs if r.get("is_error")),
        "graded": len(graded),
        "accepted": len(accepted),
        "accepted_rate": round(len(accepted) / len(graded), 4) if graded else None,
        "mean_f1": round(sum(r["f1"] for r in graded) / len(graded), 4) if graded else None,
        "durable_acceptance": {
            "pairs": len(pairs),
            "accepted_pairs": sum(1 for a, b in pairs if a in accepted and b in accepted),
        },
        "clarification_requests": sum(r["clarification_requests"] for r in graded),
        "human_active_correction_minutes": {
            "total": minutes,
            "timed_cells": len(graded) - unknown_minutes,
            "unknown_cells": unknown_minutes,
        },
        "human_decision_points": sum(r["decision_points"] for r in graded),
        "residual_defects": {
            "missing": sum(r["missing"] for r in graded),
            "extra": sum(r["extra"] for r in graded),
        },
        "cost": {
            **cost,
            "known_total_usd": known_total,
            "total_usd": None if unknown else known_total,
            "unknown_components": unknown,
        },
        "retrieval_tokens_est": sum(r["context"]["tokens_est"] for r in graded),
        "active_s": round(sum(r["active_s"] for r in graded), 1),
    }


def _mean_f1(recs: list[dict[str, Any]], condition: str, task_id: str) -> float | None:
    vals = [
        r["f1"]
        for r in recs
        if r["condition"] == condition and r["task_id"] == task_id and "f1" in r
    ]
    return sum(vals) / len(vals) if vals else None


def _correction_check(pilot: dict[str, Any], recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for task in pilot["tasks"]:
        if not task.get("uses_correction"):
            continue
        local = _mean_f1(recs, "local_context", task["id"])
        base = _mean_f1(recs, BASELINE, task["id"])
        if local is None or base is None:
            result = "not_evaluable"
        elif local > base:
            result = "gain"
        else:
            result = "no_gain"
        out.append(
            {
                "task_id": task["id"],
                "correction": task["uses_correction"],
                "local_f1": local,
                "baseline_f1": base,
                "result": result,
            }
        )
    return out


def _stale_check(pilot: dict[str, Any], recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for task in pilot["tasks"]:
        if task["role"] != "stale_trap":
            continue
        cells = [
            r
            for r in recs
            if r["condition"] == "local_context"
            and r["task_id"] == task["id"]
            and not r.get("skipped")
        ]
        expected = stale_truth(pilot, task["phase"])
        detected = (
            set().union(*(set(r["context"]["stale_fact_ids"]) for r in cells)) if cells else set()
        )
        reused = sorted(f for r in cells for f in r["context"]["fact_ids"] if f in expected)
        out.append(
            {
                "task_id": task["id"],
                "expected_stale": sorted(expected),
                "detected": sorted(detected),
                "missed": sorted(expected - detected),
                "false_alarm": sorted(detected - expected),
                "silently_reused": sorted(set(reused)),
                "result": "pass" if cells and not (expected ^ detected) and not reused else "fail",
            }
        )
    return out


def _verdict(summary: dict[str, dict[str, Any]], complete: bool) -> str:
    local, base = summary["local_context"], summary[BASELINE]
    if not complete or local["accepted_rate"] is None or base["accepted_rate"] is None:
        return "inconclusive_incomplete"
    delta = local["accepted_rate"] - base["accepted_rate"]
    return "local_context_improves_outcome" if delta > 0 else ("no_gain" if delta == 0 else "worse")


def build_report(
    pilot: dict[str, Any],
    records: list[dict[str, Any]],
    config: dict[str, Any],
    window: dict[str, Any],
    ledger: Ledger | None,
    bootstrap_usd: float | None,
    mode: str,
) -> dict[str, Any]:
    """Aggregate cells into the published report. Baseline is always listed first."""
    tasks = {t["id"]: t for t in pilot["tasks"]}
    summary = {
        c: _condition_summary(
            [r for r in records if r["condition"] == c],
            tasks,
            bootstrap_usd if c != BASELINE else 0.0,
        )
        for c in CONDITIONS
    }
    complete = all(s["skipped"] == 0 and s["errors"] == 0 for s in summary.values())
    active = sum(s["active_s"] for s in summary.values())
    elapsed = window.get("elapsed_s")
    return {
        "mode": mode,
        "pilot_revision": pilot["revision"],
        "outcome": pilot["outcome"],
        "verifier": pilot["verifier"],
        "config": config,
        "observation_window": window,
        "time_split": {
            "elapsed_s": elapsed,
            "active_s": round(active, 1),
            "waiting_s": round(elapsed - active, 1)
            if elapsed is not None and elapsed >= active
            else None,
        },
        "baseline": BASELINE,
        "conditions": summary,
        "retained_correction": _correction_check(pilot, records),
        "stale_context": _stale_check(pilot, records),
        "ceiling": None
        if ledger is None
        else {
            "ceiling_usd": ledger.ceiling_usd,
            "spent_usd": round(ledger.spent_usd, 6),
            "calls": ledger.calls,
            "stopped_reason": ledger.stopped_reason,
        },
        "complete": complete,
        "verdict": _verdict(summary, complete),
        "production_claim": {"made": False, "production_verifier": None, "review_owner": None},
        "limitations": list(LIMITATIONS),
    }
