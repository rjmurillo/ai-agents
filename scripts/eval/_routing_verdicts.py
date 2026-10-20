"""Deterministic H1 to H4 scorer for the #5426 routing comparison.

Applies `evals/routing-benchmark/PREDICTIONS.md` (`predictions-v1` plus
Amendment 1) to routing-benchmark result rows. Pure functions, no model
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
(scenario, arm, harness, repetition) key and a non-Codex harness, because
pooling duplicates or reporting a Claude run against H1 to H4 is forbidden
(PREDICTIONS.md lines 126 to 130 and 169).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

PREDICTIONS_VERSION = "predictions-v1"
CLASS_ORDINARY = "ordinary_bounded"
CLASS_FALLBACK = "fallback_reasoning"
POOLED = "pooled_all_six"
SUPPORTED = "SUPPORTED"
SUPPORTED_FOR_FALLBACK = "SUPPORTED_FOR:fallback_reasoning"
FALSIFIED = "FALSIFIED"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
SUPERSEDED_DIR = "results-2026-10-03"
CODEX = "codex"
DECISION_NOT_REGISTERED = "not pre-registered; owner decides from H1-H4"

NOT_RUN = "NOT_RUN"
ACCEPTED = "ACCEPTED"
HARNESS_FAILED = "HARNESS_FAILED"
CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
KNOWN_STATUSES = frozenset({ACCEPTED, "TASK_FAILED", HARNESS_FAILED, CONTRACT_VIOLATION, NOT_RUN})

QUALITY_MARGIN = Fraction(1, 6)  # PREDICTIONS.md line 47
DEFECT_MARGIN = Fraction(1, 2)  # line 48
ECONOMICS_FACTOR = Fraction(3, 4)  # line 50: at least 25 percent lower
HARNESS_FAILURE_LIMIT = Fraction(1, 5)  # line 66
EVIDENCE_FLOOR = 8  # line 58
FALLBACK_MIN_REPS = 2  # line 63
REPETITIONS = (1, 2, 3)  # line 29
DECISION_ORDINARY_ACCEPTED_FLOOR = 12  # line 143

INTERPRETATIONS: tuple[dict[str, object], ...] = (
    {
        "id": "I1",
        "predictions_lines": "45-46",
        "reading": (
            "Residual defects per run = scope violations + missing expected files from the "
            "stored validation, plus 1 when validation is FAIL with neither itemized (a failed "
            "follow-up check exists but rows do not list it). A run with no validation counts 0. "
            "Counts are lower bounds."
        ),
    },
    {
        "id": "I2",
        "predictions_lines": "47-49",
        "reading": (
            "Non-inferior is one-sided: comparator rate minus candidate rate <= 1/6 and "
            "candidate mean residual defects minus comparator's <= 0.5. Rates are pooled over the "
            "class (not paired per scenario) and use only non-harness-failed runs."
        ),
    },
    {
        "id": "I3",
        "predictions_lines": "50-52",
        "reading": (
            "Per accepted task = total over the arm's non-harness-failed runs in the class "
            "divided by the accepted count. Wall-clock of a run = latest invocation window end "
            "minus earliest start, so parallel fan-out is not double counted. Uncached tokens = "
            "sum over invocations of (input_tokens - cached_input_tokens) + output_tokens. Current "
            "rows carry no cached count, so input_tokens is taken as already uncached. "
            "'At least 25 percent lower' = candidate <= 0.75 x comparator on both measures. "
            "Zero accepted: economics undefined, never 'materially better'. A run with unknown "
            "time or tokens makes the arm's economics unmeasured and any verdict needing it "
            f"{INSUFFICIENT}."
        ),
    },
    {
        "id": "I4",
        "predictions_lines": "58-59",
        "reading": (
            "'Runs per arm' for the evidence floor of 8 counts non-harness-failed, non-NOT_RUN "
            "runs, because harness failures are excluded from rates (line 65)."
        ),
    },
    {
        "id": "I5",
        "predictions_lines": "60-64",
        "reading": (
            "Fallback evidence rule. Per scenario and repetition, direction = accepted(x) minus "
            "accepted(comparator) for the same repetition; a repetition with a missing or "
            "harness-failed side has no direction. 'Advantage' needs direction > 0 on at least "
            "2 of 3 repetitions in each fallback scenario and a class acceptance gap >= 1/6. "
            "'No advantage' (FALSIFIED legs) needs direction <= 0 on at least 2 of 3 repetitions "
            "in each fallback scenario and a class gap < 1/6. The H4 FALSIFIED economics leg is "
            "evaluated on the class aggregate, not per repetition."
        ),
    },
    {
        "id": "I6",
        "predictions_lines": "65-67",
        "reading": (
            "Harness-failure share of a cell = HARNESS_FAILED / (all rows except NOT_RUN). "
            "'More than 20 percent' is strictly greater than 1/5. CONTRACT_VIOLATION rows are "
            "counted as non-accepted task outcomes, not excluded."
        ),
    },
    {
        "id": "I7",
        "predictions_lines": "90-93",
        "reading": (
            "H2 SUPPORTED_FOR also needs the ordinary cells for D, A, and C to clear the "
            "harness-failure limit and the floor of 8, and ordinary D must not beat both A and "
            "C by >= 1/6. Ordinary data that cannot be judged gives INSUFFICIENT_EVIDENCE."
        ),
    },
    {
        "id": "I8",
        "predictions_lines": "106-109",
        "reading": (
            "H3 'B is not materially worse than A on both latency and tokens' is read as: it is "
            "not true that A is materially better than B on both measures. If A has zero "
            "accepted runs, A's economics is undefined, so B is not shown worse and the gap "
            "survives."
        ),
    },
    {
        "id": "I9",
        "predictions_lines": "143-145",
        "reading": (
            "'Fewer than 12 accepted ordinary runs' counts accepted ordinary_bounded runs over "
            "all input rows. 'The fallback rule for any compared arm' = arms A, C, D, E each "
            "need at least 2 non-harness-failed runs in each fallback scenario and a fallback "
            "harness-failure share of at most 1/5."
        ),
    },
    {
        "id": "I10",
        "predictions_lines": "163-170",
        "reading": (
            "Amendment 1: inputs under a results-2026-10-03 directory are pre-amendment. They "
            "may be scored alone, but every verdict is then INSUFFICIENT_EVIDENCE because they "
            "do not count toward the evidence floor. Mixing them with other files is refused."
        ),
    },
    {
        "id": "I11",
        "predictions_lines": "126-130",
        "reading": (
            "Only Codex rows are scorable. Any other harness name is refused, because H1 to H4 "
            "name Codex model families."
        ),
    },
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
        return self.status == ACCEPTED

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
    starts = [w["start"] for w in windows if w]
    ends = [w["end"] for w in windows if w]
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
        total += int(tokens_in) - int(item.get("cached_input_tokens") or 0) + int(tokens_out)
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


def cell_table(cell: Cell) -> dict[str, object]:
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
    return k_rate - c_rate <= QUALITY_MARGIN and c_def - k_def <= DEFECT_MARGIN


def materially_better(candidate: Cell, comparator: Cell) -> bool:
    """PREDICTIONS.md lines 50-52 as read in I3. Undefined economics is never better."""
    a, b = candidate.econ, comparator.econ
    if a.seconds is None or a.tokens is None or b.seconds is None or b.tokens is None:
        return False
    return a.seconds <= b.seconds * ECONOMICS_FACTOR and a.tokens <= b.tokens * ECONOMICS_FACTOR


def rate_gap_at_least_sixth(higher: Cell, lower: Cell) -> bool:
    if higher.rate is None or lower.rate is None:
        return False
    return higher.rate - lower.rate >= QUALITY_MARGIN


def rate_gap_under_sixth(higher: Cell, lower: Cell) -> bool:
    if higher.rate is None or lower.rate is None:
        return False
    return higher.rate - lower.rate < QUALITY_MARGIN


def _verdict(status: str, reason: str, **detail: object) -> dict[str, object]:
    return {"status": status, "reason": reason, **detail}


def _gate_reason(cells: Sequence[Cell], *, floor: bool) -> str | None:
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


def _economics_unmeasured(cells: Sequence[Cell]) -> str | None:
    for cell in cells:
        if not cell.econ.measured:
            return f"arm {cell.arm} in {cell.label} has runs with unknown time or tokens"
    return None


def _cell_summary(*cells: Cell) -> dict[str, object]:
    return {f"{cell.arm}:{cell.label}": cell_table(cell) for cell in cells}


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
    if _gate_reason([cell], floor=False) is not None:
        return False
    for scenario in scenarios:
        usable = sum(1 for r in runs if r.arm == arm and r.scenario_id == scenario and r.eligible)
        if usable < FALLBACK_MIN_REPS:
            return False
    return bool(scenarios)


# ------------------------------------------------------------------------ hypotheses


def evaluate_h1(runs: Sequence[Run]) -> dict[str, object]:
    c, a = cell_for(runs, "C", CLASS_ORDINARY), cell_for(runs, "A", CLASS_ORDINARY)
    detail = _cell_summary(c, a)
    reason = _gate_reason([c, a], floor=True) or _economics_unmeasured([c, a])
    if reason:
        return _verdict(INSUFFICIENT, reason, cells=detail)
    if non_inferior(c, a) and materially_better(c, a):
        return _verdict(SUPPORTED, "C non-inferior to A and materially better", cells=detail)
    if non_inferior(a, c) and materially_better(a, c):
        return _verdict(FALSIFIED, "A non-inferior to C and materially better", cells=detail)
    return _verdict(INSUFFICIENT, "neither arm is non-inferior and materially better", cells=detail)


def _h2_ordinary(runs: Sequence[Run]) -> tuple[str | None, dict[str, object]]:
    """Reason ordinary cannot clear D, or None when it shows no such advantage."""
    d, a, c = (cell_for(runs, arm, CLASS_ORDINARY) for arm in ("D", "A", "C"))
    detail = _cell_summary(d, a, c)
    reason = _gate_reason([d, a, c], floor=True)
    if reason:
        return f"ordinary class: {reason}", detail
    if rate_gap_at_least_sixth(d, a) and rate_gap_at_least_sixth(d, c):
        return "ordinary class shows the same advantage for D", detail
    return None, detail


def evaluate_h2(runs: Sequence[Run], fallback: Sequence[str]) -> dict[str, object]:
    d, a, c = (cell_for(runs, arm, CLASS_FALLBACK) for arm in ("D", "A", "C"))
    reason = _gate_reason([d, a, c], floor=False)
    ordinary_reason, ordinary_detail = _h2_ordinary(runs)
    detail = {"fallback": _cell_summary(d, a, c), "ordinary": ordinary_detail}
    if reason:
        return _verdict(INSUFFICIENT, f"fallback class: {reason}", cells=detail)
    if fallback_advantage(runs, d, a, fallback) and fallback_advantage(runs, d, c, fallback):
        if ordinary_reason:
            return _verdict(INSUFFICIENT, ordinary_reason, cells=detail)
        return _verdict(SUPPORTED_FOR_FALLBACK, "D beats A and C on fallback", cells=detail)
    if fallback_no_advantage(runs, d, a, fallback) and fallback_no_advantage(runs, d, c, fallback):
        return _verdict(FALSIFIED, "no D advantage over A or C on fallback", cells=detail)
    return _verdict(INSUFFICIENT, "fallback evidence rule not met either way", cells=detail)


def evaluate_h3(runs: Sequence[Run]) -> dict[str, object]:
    a, b = cell_for(runs, "A", None), cell_for(runs, "B", None)
    detail = _cell_summary(a, b)
    reason = _gate_reason([a, b], floor=True) or _economics_unmeasured([a, b])
    if reason:
        return _verdict(INSUFFICIENT, reason, cells=detail)
    if non_inferior(a, b) and materially_better(a, b):
        return _verdict(SUPPORTED, "A non-inferior to B pooled and materially better", cells=detail)
    if rate_gap_at_least_sixth(b, a) and not materially_better(a, b):
        return _verdict(FALSIFIED, "B leads by >= 1/6 and the gap survives economics", cells=detail)
    return _verdict(INSUFFICIENT, "neither SUPPORTED nor FALSIFIED rule holds", cells=detail)


def evaluate_h4(runs: Sequence[Run], fallback: Sequence[str]) -> dict[str, object]:
    e, a = cell_for(runs, "E", CLASS_FALLBACK), cell_for(runs, "A", CLASS_FALLBACK)
    detail = _cell_summary(e, a)
    reason = _gate_reason([e, a], floor=False)
    if reason:
        return _verdict(INSUFFICIENT, reason, cells=detail)
    if fallback_advantage(runs, e, a, fallback):
        return _verdict(SUPPORTED_FOR_FALLBACK, "E beats A on fallback", cells=detail)
    unmeasured = _economics_unmeasured([e, a])
    falsified = (
        not unmeasured
        and non_inferior(a, e)
        and materially_better(a, e)
        and _consistent(rep_directions(runs, "E", "A", fallback), advantage=False)
    )
    if falsified:
        return _verdict(FALSIFIED, "A non-inferior to E and materially better", cells=detail)
    return _verdict(INSUFFICIENT, unmeasured or "fallback evidence rule not met", cells=detail)


# -------------------------------------------------------------------------- decision


def decide(runs: Sequence[Run], fallback: Sequence[str], *, superseded: bool) -> dict[str, object]:
    """Floor check only. The H-status to decision-value mapping is not pre-registered."""
    ordinary_accepted = sum(1 for r in runs if r.klass == CLASS_ORDINARY and r.accepted)
    unmet = [arm for arm in ("A", "C", "D", "E") if not fallback_rule_met(runs, arm, fallback)]
    floor = {
        "ordinary_accepted_runs": ordinary_accepted,
        "ordinary_accepted_required": DECISION_ORDINARY_ACCEPTED_FLOOR,
        "arms_without_fallback_rule": unmet,
        "pre_amendment_inputs": superseded,
    }
    insufficient = superseded or ordinary_accepted < DECISION_ORDINARY_ACCEPTED_FLOOR or bool(unmet)
    if insufficient:
        return {
            "decision": INSUFFICIENT,
            "decision_basis": "evidence floor unmet (PREDICTIONS.md decision output)",
            "floor": floor,
        }
    return {"decision": None, "decision_basis": DECISION_NOT_REGISTERED, "floor": floor}


def _superseded_hypotheses() -> dict[str, dict[str, object]]:
    reason = "pre-amendment runs do not count toward the evidence floor (Amendment 1)"
    return {name: _verdict(INSUFFICIENT, reason) for name in ("H1", "H2", "H3", "H4")}


def score(
    runs: Sequence[Run], classes: Mapping[str, str], *, superseded: bool = False
) -> dict[str, object]:
    """Full report: cell tables, H1 to H4 statuses, decision, interpretations."""
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
            "H3": evaluate_h3(runs),
            "H4": evaluate_h4(runs, fallback),
        }
    return {
        "predictions_version": PREDICTIONS_VERSION,
        "rows_scored": sum(1 for run in runs if run.status != NOT_RUN),
        "rows_not_run": sum(1 for run in runs if run.status == NOT_RUN),
        "tables": tables,
        "hypotheses": hypotheses,
        **decide(runs, fallback, superseded=superseded),
        "interpretations": list(INTERPRETATIONS),
    }
