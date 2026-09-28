"""Durable outcome record, classifier, report, and matched comparison (REQ-042).

Pure core, stdlib only: no I/O, no subprocess, no model calls. This module
answers one question the rest of `scripts/eval/` does not: did an accepted
result stay correct after integration, or did it only pass its first check?

Fail-closed contract, mirrored from `_harness_capability.py::CapabilityStatus`
(read 2026-09-27, `scripts/eval/_harness_capability.py:52-57`):

    class CapabilityStatus(str, Enum):
        VERIFIED = "VERIFIED"
        UNSUPPORTED = "UNSUPPORTED"
        UNVERIFIED = "UNVERIFIED"

Same as canonical: a status defaults to the least favorable value on missing
or malformed evidence rather than degrading to a permissive guess.
Different than canonical: this module's fail-closed value is `Verdict.
UNVERIFIED`, not `UNSUPPORTED`, because a durable-outcome run that is missing
telemetry has not been shown to be unsupported; it has only not been shown to
be durable (REQ-042 ontology, "Missing evidence is UNVERIFIED, never PASS").

Classifier order (DESIGN-040 "Classifier order", verbatim):

    1. `deterministic_acceptance` is `FAIL`, or `capability.attempted` or
       `capability.produced_artifact` is false: `REJECTED`.
    2. Any required evidence is `UNVERIFIED`, or any durable or risk count is
       `null`: `UNVERIFIED`.
    3. `judge` is `FAIL`: `REJECTED`. The judge only downgrades.
    4. Follow-up `FAIL`, objective `FAIL`, residual defects above zero,
       rollback events above zero, or unapproved external actions above
       zero: `ACCEPTED_NOT_DURABLE`.
    5. Otherwise `ACCEPTED_DURABLE`.

The record contract and its strict parser live in `_outcome_record.py`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from _eval_common import percentile
from _outcome_record import DurableOutcomeError, Evidence, OutcomeRecord, RunConfig


class Verdict(str, Enum):
    """Per-task-run classification produced by `classify`."""

    ACCEPTED_DURABLE = "ACCEPTED_DURABLE"
    ACCEPTED_NOT_DURABLE = "ACCEPTED_NOT_DURABLE"
    REJECTED = "REJECTED"
    UNVERIFIED = "UNVERIFIED"


class ComparisonResult(str, Enum):
    """Outcome of `compare` between a baseline and a candidate configuration."""

    BETTER = "BETTER"
    WORSE = "WORSE"
    MIXED = "MIXED"
    UNVERIFIED = "UNVERIFIED"



# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def _has_unverified_required_evidence(record: OutcomeRecord) -> bool:
    required = (
        record.execution.deterministic_acceptance,
        record.execution.first_pass,
        record.durable.followup_validation,
        record.durable.objective_satisfied,
    )
    return any(evidence is Evidence.UNVERIFIED for evidence in required)


def _has_null_count(record: OutcomeRecord) -> bool:
    counts: tuple[object, ...] = (
        record.durable.residual_defects,
        record.durable.review_findings,
        record.durable.rollback_events,
        record.durable.rework_minutes,
        record.risk.security_findings,
        record.risk.unapproved_external_actions,
        record.risk.unsupported_claims,
        record.risk.unresolved_uncertainty,
    )
    return any(count is None for count in counts)


def _is_not_durable(record: OutcomeRecord) -> bool:
    # Only reached once `_has_null_count` is False, so every count read here
    # is a real int, not None.
    durable = record.durable
    return (
        durable.followup_validation is Evidence.FAIL
        or durable.objective_satisfied is Evidence.FAIL
        or (durable.residual_defects or 0) > 0
        or (durable.rollback_events or 0) > 0
        or (record.risk.unapproved_external_actions or 0) > 0
    )


def classify(record: OutcomeRecord) -> Verdict:
    """Classify one OutcomeRecord per DESIGN-040 "Classifier order" (REQ-042 AC-2 to AC-4).

    Deterministic evidence first (AC-2): a `FAIL` deterministic acceptance
    or a run that produced no artifact rejects the run whatever the judge says.
    Missing evidence next (AC-3): any required `UNVERIFIED` evidence, or any
    null durable/risk count, makes the verdict `UNVERIFIED` before the judge
    is even consulted. The judge then only downgrades (never upgrades) a
    verdict that survived the first two gates. Finally, any durability
    signal (AC-4) demotes an otherwise-accepted run to `ACCEPTED_NOT_DURABLE`.
    """
    deterministic_failed = record.execution.deterministic_acceptance is Evidence.FAIL
    no_artifact = not (record.capability.attempted and record.capability.produced_artifact)
    if deterministic_failed or no_artifact:
        return Verdict.REJECTED
    if _has_unverified_required_evidence(record) or _has_null_count(record):
        return Verdict.UNVERIFIED
    if record.execution.judge is Evidence.FAIL:
        return Verdict.REJECTED
    if _is_not_durable(record):
        return Verdict.ACCEPTED_NOT_DURABLE
    return Verdict.ACCEPTED_DURABLE


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _first_differing_field(baseline: RunConfig, other: RunConfig) -> str:
    for field in dataclasses.fields(RunConfig):
        if getattr(baseline, field.name) != getattr(other, field.name):
            return field.name
    raise DurableOutcomeError("configs report a difference but none was found")  # pragma: no cover


def _require_matched_config(records: Sequence[OutcomeRecord]) -> None:
    first = records[0].config
    for record in records[1:]:
        if record.config != first:
            field = _first_differing_field(first, record.config)
            raise DurableOutcomeError(
                f"records use different configurations for field '{field}': "
                f"{getattr(first, field)!r} != {getattr(record.config, field)!r}"
            )


def _require_unique_task_repeat(records: Sequence[OutcomeRecord]) -> None:
    seen: set[tuple[str, int]] = set()
    for record in records:
        key = (record.task_id, record.repeat)
        if key in seen:
            raise DurableOutcomeError(
                f"duplicate task_id/repeat pair: task_id={record.task_id!r} repeat={record.repeat}"
            )
        seen.add(key)


def _correction_minutes(record: OutcomeRecord) -> float:
    # A null `rework_minutes` counts as 0 here only for aggregation. The
    # classifier already turned that record UNVERIFIED, so the report status
    # still shows the missing evidence.
    rework = record.durable.rework_minutes or 0.0
    return float(record.economics.human_correction_minutes + rework)


@dataclass(frozen=True, slots=True)
class _TaskRow:
    task_id: str
    verdicts: tuple[Verdict, ...]

    @property
    def durable_accepts(self) -> int:
        return sum(1 for v in self.verdicts if v is Verdict.ACCEPTED_DURABLE)


@dataclass(frozen=True, slots=True)
class _Summary:
    """Typed intermediate for one configuration; `build_report` renders it."""

    config: RunConfig
    records: tuple[OutcomeRecord, ...]
    verdicts: tuple[Verdict, ...]
    tasks: tuple[_TaskRow, ...]

    @property
    def unverified(self) -> bool:
        return any(v is Verdict.UNVERIFIED for v in self.verdicts)

    @property
    def durable_count(self) -> int:
        return sum(1 for v in self.verdicts if v is Verdict.ACCEPTED_DURABLE)

    @property
    def costs(self) -> list[float]:
        return [r.economics.model_cost_usd + r.economics.tool_cost_usd for r in self.records]

    @property
    def corrections(self) -> list[float]:
        return [_correction_minutes(r) for r in self.records]

    @property
    def cost_per_durable_task(self) -> float | None:
        # Unrounded: the comparison must see differences below display precision.
        return sum(self.costs) / self.durable_count if self.durable_count else None

    def durable_accepts_by_task(self) -> dict[str, int]:
        return {task.task_id: task.durable_accepts for task in self.tasks}

    def repeats_by_task(self) -> dict[str, int]:
        return {task.task_id: len(task.verdicts) for task in self.tasks}


def _per_durable_task(values: Sequence[float], durable_count: int) -> float | None:
    # Costs of rejected runs stay in the numerator: failed attempts are part
    # of the price of an accepted result (DESIGN-040 "Report").
    return round(sum(values) / durable_count, 4) if durable_count else None


def _group_tasks(
    records: Sequence[OutcomeRecord], verdicts: Sequence[Verdict]
) -> tuple[_TaskRow, ...]:
    by_task: dict[str, list[Verdict]] = {}
    for record, verdict in zip(records, verdicts, strict=True):
        by_task.setdefault(record.task_id, []).append(verdict)
    return tuple(_TaskRow(task_id, tuple(found)) for task_id, found in by_task.items())


def _summarize(records: Sequence[OutcomeRecord]) -> _Summary:
    if not records:
        raise DurableOutcomeError("a configuration requires at least one record")
    _require_matched_config(records)
    _require_unique_task_repeat(records)
    verdicts = tuple(classify(record) for record in records)
    return _Summary(
        config=records[0].config,
        records=tuple(records),
        verdicts=verdicts,
        tasks=_group_tasks(records, verdicts),
    )


def _verdict_counts(verdicts: Sequence[Verdict]) -> dict[str, int]:
    counts = {verdict.value: 0 for verdict in Verdict}
    for verdict in verdicts:
        counts[verdict.value] += 1
    return counts


def _percentile_triplet(values: Sequence[float]) -> dict[str, float]:
    return {
        "p10": round(percentile(values, 10.0), 4),
        "p50": round(percentile(values, 50.0), 4),
        "p90": round(percentile(values, 90.0), 4),
    }


def _residual_risk(summary: _Summary) -> int:
    total = 0
    for record, verdict in zip(summary.records, summary.verdicts, strict=True):
        total += record.risk.security_findings or 0
        total += record.risk.unapproved_external_actions or 0
        total += record.risk.unsupported_claims or 0
        total += record.risk.unresolved_uncertainty or 0
        if verdict in (Verdict.ACCEPTED_DURABLE, Verdict.ACCEPTED_NOT_DURABLE):
            total += record.durable.residual_defects or 0
    return total


def _headline(summary: _Summary) -> dict[str, object]:
    return {
        "cost_per_accepted_durable_task_usd": _per_durable_task(
            summary.costs, summary.durable_count
        ),
        "correction_minutes_per_accepted_durable_task": _per_durable_task(
            summary.corrections, summary.durable_count
        ),
        "residual_risk": _residual_risk(summary),
    }


def _task_row_json(task: _TaskRow) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "repeats": len(task.verdicts),
        "durable_accepts": task.durable_accepts,
        "verdicts": [v.value for v in task.verdicts],
    }


def _render(summary: _Summary) -> dict[str, object]:
    return {
        "status": "UNVERIFIED" if summary.unverified else "VERIFIED",
        "config": dataclasses.asdict(summary.config),
        "verdict_counts": _verdict_counts(summary.verdicts),
        "per_task": [_task_row_json(task) for task in summary.tasks],
        "zero_success_tasks": [t.task_id for t in summary.tasks if t.durable_accepts == 0],
        "all_success_tasks": [
            t.task_id for t in summary.tasks if t.durable_accepts == len(t.verdicts)
        ],
        "cost_percentiles_usd": _percentile_triplet(summary.costs),
        "correction_minutes_percentiles": _percentile_triplet(summary.corrections),
        "headline": _headline(summary),
    }


def build_report(records: Sequence[OutcomeRecord]) -> dict[str, object]:
    """Build one ConfigurationReport from OutcomeRecords sharing one RunConfig.

    REQ-042 AC-5: per-task verdicts, zero-success and all-success tasks, and
    p10/p50/p90 of cost and correction time. AC-6: the headline (cost per
    accepted durable task, correction minutes per accepted durable task,
    residual risk), `null` when no task is accepted durable.

    Refuses (DurableOutcomeError) when the records do not share one RunConfig
    (DESIGN-040 "Report": one file holds one configuration) or when a
    `task_id`/`repeat` pair repeats (REQ-042 data-model invariant 3).
    """
    return _render(_summarize(records))


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _require_configs_match_except_control(baseline: RunConfig, candidate: RunConfig) -> None:
    for field in dataclasses.fields(RunConfig):
        if field.name == "control":
            continue
        base_value = getattr(baseline, field.name)
        candidate_value = getattr(candidate, field.name)
        if base_value != candidate_value:
            raise DurableOutcomeError(
                f"comparison configs differ in field '{field.name}': "
                f"{base_value!r} != {candidate_value!r}"
            )


def _require_same_task_sets(baseline: _Summary, candidate: _Summary) -> None:
    baseline_ids = set(baseline.durable_accepts_by_task())
    candidate_ids = set(candidate.durable_accepts_by_task())
    if baseline_ids != candidate_ids:
        raise DurableOutcomeError(
            "comparison task sets differ: "
            f"missing from candidate={sorted(baseline_ids - candidate_ids)}, "
            f"missing from baseline={sorted(candidate_ids - baseline_ids)}"
        )
    # Extra repeats would add durable accepts without a better success rate.
    base_repeats = baseline.repeats_by_task()
    cand_repeats = candidate.repeats_by_task()
    differing = sorted(t for t in base_repeats if base_repeats[t] != cand_repeats[t])
    if differing:
        raise DurableOutcomeError(f"comparison repeat counts differ for tasks {differing}")


def _has_zero_drop(other: _Summary, this: _Summary) -> bool:
    """True when a task with >=1 durable accept in `other` has zero in `this`."""
    this_by_task = this.durable_accepts_by_task()
    return any(
        accepts >= 1 and this_by_task[task_id] == 0
        for task_id, accepts in other.durable_accepts_by_task().items()
    )


def _cost_no_worse(this: _Summary, other: _Summary) -> bool:
    other_cost = other.cost_per_durable_task
    if other_cost is None:
        return True
    this_cost = this.cost_per_durable_task
    return this_cost is not None and this_cost <= other_cost


def _dominates(this: _Summary, other: _Summary) -> bool:
    """True when `this` meets every BETTER criterion against `other`."""
    return (
        this.durable_count >= other.durable_count
        and _cost_no_worse(this, other)
        and not _has_zero_drop(other, this)
    )


def _compare_summaries(baseline: _Summary, candidate: _Summary) -> ComparisonResult:
    if baseline.unverified or candidate.unverified:
        return ComparisonResult.UNVERIFIED
    better = _dominates(candidate, baseline)
    worse = _dominates(baseline, candidate)
    if better and not worse:
        return ComparisonResult.BETTER
    if worse and not better:
        return ComparisonResult.WORSE
    return ComparisonResult.MIXED


def compare(
    baseline_records: Sequence[OutcomeRecord], candidate_records: Sequence[OutcomeRecord]
) -> dict[str, object]:
    """Compare a baseline and candidate configuration on the same task set.

    REQ-042 AC-7: refuses when the configs differ in any field except
    `control`, or the task sets differ, naming the differing field or the
    missing task ids. AC-8: `BETTER` requires at least as many accepted
    durable tasks, no higher cost per accepted durable task, and no task that
    drops from one or more durable accepts to zero; `WORSE` is the mirror;
    anything else is `MIXED`. Either side `UNVERIFIED` makes the comparison
    `UNVERIFIED` (DESIGN-040 "Comparison").
    """
    baseline = _summarize(baseline_records)
    candidate = _summarize(candidate_records)
    _require_configs_match_except_control(baseline.config, candidate.config)
    _require_same_task_sets(baseline, candidate)
    return {
        "baseline": _render(baseline),
        "candidate": _render(candidate),
        "result": _compare_summaries(baseline, candidate).value,
    }
