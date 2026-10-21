"""Run parsing, per-arm aggregation, and comparison primitives for the verdict scorer.

Split from `_routing_verdicts.py` by cohesion: this module turns result rows into
`Cell` aggregates and answers the shared questions (non-inferior, materially
better, harness-failure gate). The hypothesis and decision rules stay in
`_routing_verdicts.py`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from _routing_verdict_constants import (
    ACCEPTED,
    CODEX,
    CONTRACT_VIOLATION,
    DEFECT_MARGIN,
    ECONOMICS_FACTOR,
    EVIDENCE_FLOOR,
    HARNESS_FAILED,
    HARNESS_FAILURE_LIMIT,
    KNOWN_STATUSES,
    NOT_RUN,
    POOLED,
    QUALITY_MARGIN,
    REPETITIONS,
)


class VerdictInputError(ValueError):
    """The inputs cannot be scored without breaking a pre-registered rule."""


@dataclass(frozen=True, slots=True)
class Run:
    scenario_id: str
    klass: str
    arm: str
    repetition: int
    status: str
    seconds: float | None
    tokens: int | None
    residual: int

    @property
    def accepted(self) -> bool:
        return bool(self.status == ACCEPTED)

    @property
    def eligible(self) -> bool:
        """Counts toward rates: neither a harness failure nor a run that never happened."""
        return self.status not in (HARNESS_FAILED, NOT_RUN)


@dataclass(frozen=True, slots=True)
class Econ:
    """Economics per accepted task. `None` fields mean undefined (zero accepted)."""

    measured: bool
    seconds: Fraction | None
    tokens: Fraction | None


@dataclass(frozen=True, slots=True)
class Cell:
    arm: str
    label: str
    attempted: int
    not_run: int
    harness_failed: int
    eligible: int
    accepted: int
    task_failed: int
    contract_violation: int
    residual_total: int
    seconds_total: Fraction | None
    tokens_total: Fraction | None

    @property
    def harness_failure_share(self) -> Fraction | None:
        return Fraction(self.harness_failed, self.attempted) if self.attempted else None

    @property
    def rate(self) -> Fraction | None:
        return Fraction(self.accepted, self.eligible) if self.eligible else None

    @property
    def mean_residual(self) -> Fraction | None:
        return Fraction(self.residual_total, self.eligible) if self.eligible else None

    @property
    def econ(self) -> Econ:
        measured = self.seconds_total is not None and self.tokens_total is not None
        if not measured or self.accepted == 0:
            return Econ(measured, None, None)
        assert self.seconds_total is not None and self.tokens_total is not None
        return Econ(True, self.seconds_total / self.accepted, self.tokens_total / self.accepted)


# --------------------------------------------------------------------------- parsing


def _harness_name(row: Mapping[str, Any]) -> str:
    harness = row.get("harness")
    if isinstance(harness, Mapping):
        return str(harness.get("name"))
    return str(harness)


def _wall_clock(invocations: Sequence[Mapping[str, Any]]) -> float | None:
    windows = [item.get("window") for item in invocations]
    if not windows or any(not isinstance(w, Mapping) for w in windows):
        return None
    starts = [w.get("start") for w in windows]
    ends = [w.get("end") for w in windows]
    if any(v is None for v in starts + ends):
        return None
    return float(max(ends) - min(starts))


def _uncached_tokens(invocations: Sequence[Mapping[str, Any]]) -> int | None:
    if not invocations:
        return None
    total = 0
    for item in invocations:
        tokens_in, tokens_out = item.get("input_tokens"), item.get("output_tokens")
        if tokens_in is None or tokens_out is None:
            return None
        total += int(tokens_in) + int(tokens_out)
    return total


def _residual_defects(row: Mapping[str, Any]) -> int:
    validation = row.get("validation")
    if not isinstance(validation, Mapping):
        return 0
    itemized = len(validation.get("scope_violations") or ()) + len(
        validation.get("missing_expected") or ()
    )
    if itemized == 0 and validation.get("verdict") == "FAIL":
        return 1
    return itemized


def _parse_row(row: Mapping[str, Any], classes: Mapping[str, str]) -> Run:
    scenario_id, status = row.get("scenario_id"), row.get("status")
    if scenario_id not in classes:
        raise VerdictInputError(f"scenario {scenario_id!r} is not in the corpus")
    if status not in KNOWN_STATUSES:
        raise VerdictInputError(f"{scenario_id}: unknown status {status!r}")
    repetition = row.get("repetition")
    if not isinstance(repetition, int) or isinstance(repetition, bool):
        raise VerdictInputError(f"{scenario_id}/{row.get('arm')}: row has no integer repetition")
    if repetition not in REPETITIONS:
        raise VerdictInputError(
            f"{scenario_id}/{row.get('arm')}: repetition {repetition} is outside the "
            f"registered design {list(REPETITIONS)}"
        )
    invocations = row.get("invocations") or []
    return Run(
        scenario_id=str(scenario_id),
        klass=classes[str(scenario_id)],
        arm=str(row.get("arm")),
        repetition=repetition,
        status=str(status),
        seconds=_wall_clock(invocations),
        tokens=_uncached_tokens(invocations),
        residual=_residual_defects(row),
    )


def parse_runs(rows: Sequence[Mapping[str, Any]], classes: Mapping[str, str]) -> list[Run]:
    """Rows to `Run`s. Refuses non-Codex harnesses and duplicate keys."""
    seen: set[tuple[str, str, int]] = set()
    runs: list[Run] = []
    for row in rows:
        harness = _harness_name(row)
        if harness != CODEX:
            raise VerdictInputError(f"harness {harness!r} is not scorable; only {CODEX!r} rows are")
        run = _parse_row(row, classes)
        key = (run.scenario_id, run.arm, run.repetition)
        if key in seen:
            raise VerdictInputError(f"duplicate row for scenario/arm/repetition {key}")
        seen.add(key)
        runs.append(run)
    return runs


# --------------------------------------------------------------------------- cells


def _sum_or_none(values: Sequence[float | int | None]) -> Fraction | None:
    if any(value is None for value in values):
        return None
    return sum((Fraction(value) for value in values if value is not None), Fraction(0))


def build_cell(arm: str, label: str, runs: Sequence[Run]) -> Cell:
    """One arm over `runs`, which the caller already restricted to a class or pool."""
    scored = [run for run in runs if run.eligible]
    return Cell(
        arm=arm,
        label=label,
        attempted=sum(1 for run in runs if run.status != NOT_RUN),
        not_run=sum(1 for run in runs if run.status == NOT_RUN),
        harness_failed=sum(1 for run in runs if run.status == HARNESS_FAILED),
        eligible=len(scored),
        accepted=sum(1 for run in scored if run.accepted),
        task_failed=sum(1 for run in scored if run.status == "TASK_FAILED"),
        contract_violation=sum(1 for run in scored if run.status == CONTRACT_VIOLATION),
        residual_total=sum(run.residual for run in scored),
        seconds_total=_sum_or_none([run.seconds for run in scored]),
        tokens_total=_sum_or_none([run.tokens for run in scored]),
    )


def cell_for(runs: Sequence[Run], arm: str, klass: str | None) -> Cell:
    """Cell for `arm` in `klass`; `klass=None` pools all classes (H3 only)."""
    mine = [r for r in runs if r.arm == arm and (klass is None or r.klass == klass)]
    return build_cell(arm, klass or POOLED, mine)


def _fraction_value(value: Fraction | None) -> float | None:
    return None if value is None else float(value)


def cell_table(cell: Cell) -> dict[str, Any]:
    econ = cell.econ
    return {
        "arm": cell.arm,
        "class": cell.label,
        "runs": cell.attempted,
        "accepted": cell.accepted,
        "task_failed": cell.task_failed,
        "contract_violation": cell.contract_violation,
        "harness_failed": cell.harness_failed,
        "not_run": cell.not_run,
        "harness_failure_share": _fraction_value(cell.harness_failure_share),
        "acceptance_rate": _fraction_value(cell.rate),
        "mean_residual_defects": _fraction_value(cell.mean_residual),
        "economics_measured": econ.measured,
        "mean_seconds_per_accepted": _fraction_value(econ.seconds),
        "mean_uncached_tokens_per_accepted": _fraction_value(econ.tokens),
    }


# ----------------------------------------------------------------- comparison rules


def non_inferior(candidate: Cell, comparator: Cell) -> bool:
    """PREDICTIONS.md lines 47-49 as read in I2."""
    c_rate, k_rate = candidate.rate, comparator.rate
    c_def, k_def = candidate.mean_residual, comparator.mean_residual
    if c_rate is None or k_rate is None or c_def is None or k_def is None:
        return False
    return bool(k_rate - c_rate <= QUALITY_MARGIN and c_def - k_def <= DEFECT_MARGIN)


def materially_better(candidate: Cell, comparator: Cell) -> bool:
    """PREDICTIONS.md lines 50-52 as read in I3. Undefined economics is never better."""
    a, b = candidate.econ, comparator.econ
    if a.seconds is None or a.tokens is None or b.seconds is None or b.tokens is None:
        return False
    return bool(
        a.seconds <= b.seconds * ECONOMICS_FACTOR and a.tokens <= b.tokens * ECONOMICS_FACTOR
    )


def rate_gap_at_least_sixth(higher: Cell, lower: Cell) -> bool:
    if higher.rate is None or lower.rate is None:
        return False
    return bool(higher.rate - lower.rate >= QUALITY_MARGIN)


def rate_gap_under_sixth(higher: Cell, lower: Cell) -> bool:
    if higher.rate is None or lower.rate is None:
        return False
    return bool(higher.rate - lower.rate < QUALITY_MARGIN)


def gate_reason(cells: Sequence[Cell], *, floor: bool) -> str | None:
    """First reason a set of cells cannot support a verdict, or None."""
    for cell in cells:
        name = f"arm {cell.arm} in {cell.label}"
        share = cell.harness_failure_share
        if share is None:
            return f"{name} has no runs"
        if share > HARNESS_FAILURE_LIMIT:
            return f"{name} has {cell.harness_failed} of {cell.attempted} harness failures (>20%)"
        if floor and cell.eligible < EVIDENCE_FLOOR:
            return f"{name} has {cell.eligible} scored runs, below the floor of {EVIDENCE_FLOOR}"
    return None


def economics_unmeasured(cells: Sequence[Cell]) -> str | None:
    for cell in cells:
        if not cell.econ.measured:
            return f"arm {cell.arm} in {cell.label} has runs with unknown time or tokens"
    return None


def cell_summary(*cells: Cell) -> dict[str, Any]:
    return {f"{cell.arm}:{cell.label}": cell_table(cell) for cell in cells}
