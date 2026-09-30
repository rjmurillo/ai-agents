"""Variance across repetitions for durable-outcome records (issue #5768).

`build_report` in `_durable_outcome.py` folds every repetition of a task into
one per-task row. This module keeps the repetitions apart: for each repeat
index it reports accepted-durable, accepted-not-durable, and rejected counts
and cost per accepted durable task, then the mean, sample standard deviation,
minimum, and maximum of those per-repeat numbers across repeats.

It computes descriptive statistics only. With three repeats a standard
deviation is a rough spread, not a confidence interval, and this module makes
no significance claim. A repeat with no durable acceptance has no cost per
durable acceptance, so that repeat is left out of the cost statistics and
counted in `repeats_without_durable`.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from _durable_outcome import Verdict, classify
from _outcome_record import OutcomeRecord


def _spread(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "stdev": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        # Sample standard deviation needs two values; one value has no spread estimate.
        "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else None,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


@dataclass(frozen=True, slots=True)
class _RepeatRow:
    repeat: int
    tasks: int
    accepted_durable: int
    accepted_not_durable: int
    rejected: int
    unverified: int
    cost_usd: float
    cost_per_durable_usd: float | None


def _repeat_row(repeat: int, records: Sequence[OutcomeRecord]) -> _RepeatRow:
    verdicts = [classify(record) for record in records]
    durable = sum(1 for v in verdicts if v is Verdict.ACCEPTED_DURABLE)
    cost = sum(r.economics.model_cost_usd + r.economics.tool_cost_usd for r in records)
    return _RepeatRow(
        repeat=repeat,
        tasks=len(records),
        accepted_durable=durable,
        accepted_not_durable=sum(1 for v in verdicts if v is Verdict.ACCEPTED_NOT_DURABLE),
        rejected=sum(1 for v in verdicts if v is Verdict.REJECTED),
        unverified=sum(1 for v in verdicts if v is Verdict.UNVERIFIED),
        cost_usd=round(cost, 6),
        cost_per_durable_usd=round(cost / durable, 4) if durable else None,
    )


def _task_rows(records: Sequence[OutcomeRecord]) -> list[dict[str, object]]:
    by_task: dict[str, list[Verdict]] = {}
    for record in sorted(records, key=lambda r: (r.task_id, r.repeat)):
        by_task.setdefault(record.task_id, []).append(classify(record))
    return [
        {
            "task_id": task_id,
            "repeats": len(verdicts),
            "durable_accepts": sum(1 for v in verdicts if v is Verdict.ACCEPTED_DURABLE),
            "verdicts": [v.value for v in verdicts],
            "mixed": len(set(verdicts)) > 1,
        }
        for task_id, verdicts in by_task.items()
    ]


def _require_same_tasks(by_repeat: dict[int, list[OutcomeRecord]]) -> None:
    """Refuse repeats that cover different tasks, so a missing task is not read as variance."""
    task_sets = {index: {r.task_id for r in group} for index, group in by_repeat.items()}
    expected = set().union(*task_sets.values())
    short = {
        index: sorted(expected - found) for index, found in task_sets.items() if found != expected
    }
    if short:
        raise ValueError(f"repeats cover different tasks; missing by repeat: {short}")


def repetition_summary(records: Sequence[OutcomeRecord]) -> dict[str, object]:
    """Per-repeat counts and across-repeat spread for one configuration's records."""
    if not records:
        raise ValueError("repetition_summary needs at least one record")
    by_repeat: dict[int, list[OutcomeRecord]] = {}
    for record in records:
        by_repeat.setdefault(record.repeat, []).append(record)
    _require_same_tasks(by_repeat)
    rows = [_repeat_row(index, group) for index, group in sorted(by_repeat.items())]
    costs = [r.cost_per_durable_usd for r in rows if r.cost_per_durable_usd is not None]
    tasks = _task_rows(records)
    return {
        "repeats": len(rows),
        "per_repeat": [asdict(row) for row in rows],
        "accepted_durable_spread": _spread([float(r.accepted_durable) for r in rows]),
        "cost_per_durable_spread_usd": _spread(costs),
        "repeats_without_durable": len(rows) - len(costs),
        "per_task": tasks,
        "tasks_with_mixed_verdicts": [row["task_id"] for row in tasks if row["mixed"]],
    }
