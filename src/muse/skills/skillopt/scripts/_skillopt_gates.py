"""Validation gates and scoring over held-out eval splits."""

from __future__ import annotations

import re
from typing import Any

from _skillopt_patching import SkillOptError

# Statuses that mark a selection task as unusable for gating.
BAD_TASK_STATUSES = ("invalid", "exposed")

# Values the optional eval-manifest "scorer" field may take.
SCORER_VALUES = ("deterministic", "nondeterministic")

_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")

# Next step printed with REJECT_CEILING. The incumbent already passes every
# held-out task, so no candidate can show a gain on this split.
CEILING_HINT = (
    "The incumbent already passes every held-out task, so no candidate can show a gain. "
    "Freeze a new sel set of harder tasks that sample the failure mode, re-score the "
    "incumbent, then author a fresh candidate. "
    "Never re-gate this candidate on tasks written after it. "
    "For a first draft whose sel tasks came from its own requirements, hand back to skillforge."
)


# --------------------------------------------------------------------------- #
# Validation gates: scalar strict-greater and per-task strict Pareto
# --------------------------------------------------------------------------- #
def gate(candidate_score: float, incumbent_best: float) -> bool:
    """True iff the candidate strictly improves on the incumbent best.

    Strict, not >=: a tie is a reject. Equal score means the edit bought nothing,
    so it does not earn the added text. This is the load-bearing rule.
    """
    return candidate_score > incumbent_best


def _task_status(tasks: dict[str, Any], tid: str) -> str | None:
    """The string `status` of task `tid`, or None when it has no entry or status."""
    entry = tasks.get(tid)
    if not isinstance(entry, dict) or "status" not in entry:
        return None
    status = entry["status"]
    if not isinstance(status, str):
        raise SkillOptError(f"task {tid!r} status must be a string")
    return status


def _assert_selection_usable(eval_set: dict[str, Any], task_ids: list[str]) -> None:
    """Refuse to gate on selection tasks that are exposed or marked unusable."""
    exposed = eval_set.get("exposed", [])
    if not isinstance(exposed, list):
        raise SkillOptError("eval set 'exposed' must be a list of task ids")
    tasks = eval_set.get("tasks", {})
    if not isinstance(tasks, dict):
        raise SkillOptError("eval set 'tasks' must be an object keyed by task id")
    bad: list[str] = []
    for tid in task_ids:
        if tid in exposed or _task_status(tasks, tid) in BAD_TASK_STATUSES:
            bad.append(tid)
    if bad:
        raise SkillOptError(
            f"selection task(s) exposed or invalid: {', '.join(bad)}; "
            "replace them with untouched holdout tasks before gating"
        )


def _passing(task_ids: list[str], results: dict[str, Any]) -> set[str]:
    """Task ids whose result is the literal True. Truthy values do not count."""
    return {tid for tid in task_ids if results.get(tid) is True}


def _unverified(task_ids: list[str], *result_sets: dict[str, Any]) -> list[str]:
    """Task ids whose value is missing or not a bool in ANY of the result sets."""
    return [
        tid
        for tid in task_ids
        if any(not isinstance(results.get(tid), bool) for results in result_sets)
    ]


def _null_control(
    task_ids: list[str], incumbent: set[str], null_results: dict[str, Any], gains: list[str]
) -> dict[str, Any]:
    """Compare a no-op rerun of the incumbent against the incumbent itself."""
    null_pass = _passing(task_ids, null_results)
    null_gains = [t for t in task_ids if t in null_pass and t not in incumbent]
    null_regressions = [t for t in task_ids if t in incumbent and t not in null_pass]
    return {
        "null_gains": null_gains,
        "null_regressions": null_regressions,
        "genuine_gains": [t for t in gains if t not in null_gains],
    }


def _verdict(report: dict[str, Any], has_null: bool) -> str:
    """Map a pair-gate report to its verdict string."""
    if report["unverified"]:
        return "REJECT_UNVERIFIED"
    if has_null:
        null_moved = report["null_gains"] or report["null_regressions"]
        if null_moved and not report["genuine_gains"]:
            return "REJECT_NULL_CONTROL"
    if (
        report["split"] == "sel"
        and report["incumbent_passes"] == report["selection_tasks"]
        and not report["regressions"]
    ):
        return "REJECT_CEILING"
    gained = report["genuine_gains"] if has_null else report["gains"]
    return "ACCEPT_PARETO" if gained and not report["regressions"] else "REJECT"


def _assert_null_ran_on_incumbent(incumbent_sha256: object, null_sha256: object) -> None:
    """The null control must come from a rerun of the byte-identical incumbent."""
    for value in (incumbent_sha256, null_sha256):
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value.strip()):
            raise SkillOptError(
                "null control needs --incumbent-sha256 and --null-sha256 "
                "(64 hex characters each, from `skillopt.py hash`)"
            )
    if str(incumbent_sha256).strip().lower() != str(null_sha256).strip().lower():
        raise SkillOptError("null control did not run on the byte-identical incumbent")


def _assert_gate_preconditions(
    eval_set: dict[str, Any],
    split: str,
    null_results: dict[str, Any] | None,
    incumbent_sha256: object,
    null_sha256: object,
) -> None:
    """Scorer declaration and null-control provenance checks, before comparing."""
    scorer = eval_set.get("scorer")
    if scorer is not None and scorer not in SCORER_VALUES:
        raise SkillOptError(f"eval set 'scorer' must be one of {SCORER_VALUES}, got {scorer!r}")
    if null_results is None:
        if split == "sel" and scorer == "nondeterministic":
            raise SkillOptError("nondeterministic scorer requires --null-results")
        return
    _assert_null_ran_on_incumbent(incumbent_sha256, null_sha256)


def pair_gate(
    eval_set: dict[str, Any],
    incumbent_results: dict[str, Any],
    candidate_results: dict[str, Any],
    split: str = "sel",
    null_results: dict[str, Any] | None = None,
    *,
    incumbent_sha256: str | None = None,
    null_sha256: str | None = None,
) -> dict[str, Any]:
    """Compare per-task results and accept only a strict Pareto improvement.

    The candidate must preserve every incumbent pass and add at least one new
    pass. This lets a declared resource objective such as context reduction
    count as a real gain without allowing an aggregate score to hide a semantic
    regression.

    Checks beyond the Pareto rule:
      - on the "sel" split only, tasks listed in eval_set["exposed"] or marked
        invalid/exposed raise SkillOptError (the gate would be measuring a
        leaked task). Other splits such as "train" may hold exposed tasks;
      - eval_set["scorer"], when present, is "deterministic" or
        "nondeterministic"; a nondeterministic scorer on "sel" requires
        null_results;
      - a task whose result is missing or not a bool in any result set makes
        the verdict REJECT_UNVERIFIED (only literal True is a pass);
      - when null_results (a no-op rerun of the byte-identical incumbent) is
        given, gains the null control also shows are noise, not improvement.
        If the null run moved and no genuine gain remains, REJECT_NULL_CONTROL.
        null_results requires incumbent_sha256 and null_sha256 (from the
        `hash` subcommand) and they must match, proving the null run used the
        byte-identical incumbent;
      - on the "sel" split, an incumbent that already passes every task with
        no candidate regression is REJECT_CEILING, not REJECT: no gain is
        possible, so the report adds a `hint` naming the next step. Verdict
        precedence is UNVERIFIED, NULL_CONTROL, CEILING, then ACCEPT_PARETO or
        REJECT.
    """
    task_ids = _split_task_ids(eval_set, split)
    _assert_gate_preconditions(eval_set, split, null_results, incumbent_sha256, null_sha256)
    if split == "sel":
        _assert_selection_usable(eval_set, task_ids)
    result_sets = [incumbent_results, candidate_results]
    if null_results is not None:
        result_sets.append(null_results)

    incumbent_set = _passing(task_ids, incumbent_results)
    candidate_set = _passing(task_ids, candidate_results)
    gains = [t for t in task_ids if t in candidate_set and t not in incumbent_set]
    regressions = [t for t in task_ids if t in incumbent_set and t not in candidate_set]
    report: dict[str, Any] = {
        "split": split,
        "selection_tasks": len(task_ids),
        "incumbent_passes": len(incumbent_set),
        "candidate_passes": len(candidate_set),
        "gains": gains,
        "regressions": regressions,
        "unverified": _unverified(task_ids, *result_sets),
    }
    if null_results is not None:
        report.update(_null_control(task_ids, incumbent_set, null_results, gains))
    report["verdict"] = _verdict(report, null_results is not None)
    report["accepted"] = report["verdict"] == "ACCEPT_PARETO"
    if report["verdict"] == "REJECT_CEILING":
        report["hint"] = CEILING_HINT
    ordered = ["accepted", "verdict", *[k for k in report if k not in ("accepted", "verdict")]]
    return {key: report[key] for key in ordered}


# --------------------------------------------------------------------------- #
# Scoring: count pass/fail on the held-out split. No eval set, no score, no gate.
# --------------------------------------------------------------------------- #
def _split_task_ids(eval_set: dict[str, Any], split: str) -> list[str]:
    """Return a nonempty, unique task-id list for a declared eval split."""
    splits = eval_set.get("splits")
    if not isinstance(splits, dict) or split not in splits:
        raise SkillOptError(f"eval set has no '{split}' split")
    task_ids = splits[split]
    if not isinstance(task_ids, list) or not task_ids:
        raise SkillOptError(f"'{split}' split is empty; the gate would be vacuous")
    if not all(isinstance(task_id, str) and task_id for task_id in task_ids):
        raise SkillOptError(f"'{split}' split must contain nonempty string task ids")
    if len(set(task_ids)) != len(task_ids):
        raise SkillOptError(f"'{split}' split contains duplicate task ids")
    return task_ids


def score_results(eval_set: dict[str, Any], results: dict[str, Any], split: str = "sel") -> float:
    """Pass-rate over the named split. eval_set names which task ids are held out.

    eval_set: {"splits": {"sel": [task_id, ...], "train": [...]}, ...}
    results : {"<task_id>": true|false, ...}  (verifier pass/fail per task)
    Returns pass count / split size in [0,1]. A held-out task with no result is a
    fail (you do not get credit for a task you did not run).
    """
    task_ids = _split_task_ids(eval_set, split)
    return len(_passing(task_ids, results)) / len(task_ids)
