"""Run one planned routing combination and compare paired runs (issue #5424).

`run_planned` executes the invocation DAG through a `Backend`, grades each
round with the deterministic grader, and classifies the outcome. It refuses a
plan row that was not `PLANNED`, so an unsupported or unverified combination
cannot spend anything through this function.

Detected here, each as a stable code in `RunResult.violations`:

* `model_mismatch`, `effort_mismatch`: backend evidence differs from the request;
* `silent_model_inheritance`, `silent_effort_inheritance`: the child ran the
  parent's model or effort instead of the requested one (#5423 negative
  control: a requested child that silently inherits must fail);
* `concurrency_ceiling_exceeded`: more children ran at once than allowed;
* `reviewer_isolation_broken`: an isolated reviewer saw producer context;
* `fresh_context_missing`, `fresh_session_reused`: a fresh-context boundary
  was not honored;
* `handoff_missing`, `handoff_mismatch`: the implementation did not read the
  artifact the plan produced;
* `correction_budget_exceeded`.

Recorded without failing the run, as `notes`: an unverified model or effort
(no backend evidence) and unavailable telemetry. Neither is turned into a
value.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from _routing_backend import IMPLEMENT_INVOCATION_ID, PLAN_INVOCATION_ID, Backend
from _routing_config import Strategy
from _routing_dag import build_requests, correction_request
from _routing_grader import GradeResult
from _routing_grader import Verdict as GradeVerdict
from _routing_plan import HarnessComparison, PlanRow, RowStatus
from _routing_result import (
    CHILD_ROLES,
    FailureKind,
    InvocationRecord,
    InvocationRequest,
    Observation,
    RunResult,
    RunStatus,
    Validation,
    Verdict,
    estimate_cost_usd,
    sum_known,
    value_verdict,
)
from _routing_scenario import Scenario


@dataclass(frozen=True, slots=True)
class PairVerdict:
    status: str
    reasons: tuple[str, ...]
    telemetry_comparable: bool


def _record(request: InvocationRequest, backend: Backend, scenario: Scenario) -> InvocationRecord:
    seen = backend.invoke(request, scenario)
    model_verdict = value_verdict(request.model, seen.observed_model, seen.evidence)
    return InvocationRecord(
        request=request,
        observation=seen,
        model_verdict=model_verdict,
        effort_verdict=value_verdict(request.effort, seen.observed_effort, seen.evidence),
        cost_usd=_cost(request, seen, model_verdict),
    )


def _cost(request: InvocationRequest, seen: Observation, verdict: Verdict) -> float | None:
    """Price the model that backend evidence says ran. Unknown billing model: no cost."""
    if verdict is Verdict.HONORED:
        billed: str | None = request.model
    elif verdict is Verdict.MISMATCH:
        billed = seen.observed_model
    else:
        billed = None
    if billed is None:
        return None
    cost: float | None = estimate_cost_usd(billed, seen.input_tokens, seen.output_tokens)
    return cost


def _harness_failed(record: InvocationRecord) -> bool:
    return record.observation.failure is FailureKind.HARNESS


def _validation(grade: GradeResult) -> Validation:
    return Validation(
        grade.verdict.value, grade.changed_paths, grade.scope_violations, grade.missing_expected
    )


def _execute(
    strategy: Strategy, scenario: Scenario, backend: Backend
) -> tuple[list[InvocationRecord], Validation | None, int, bool]:
    records: list[InvocationRecord] = []
    for request in build_requests(strategy, scenario):
        records.append(_record(request, backend, scenario))
        if _harness_failed(records[-1]):
            return records, None, 0, True
    grade = backend.grade(scenario, 0)
    rounds = 0
    while grade.verdict is GradeVerdict.FAIL and rounds < strategy.max_correction_rounds:
        rounds += 1
        request = correction_request(strategy, scenario, rounds, records[-1].request.invocation_id)
        records.append(_record(request, backend, scenario))
        if _harness_failed(records[-1]):
            return records, None, rounds, True
        grade = backend.grade(scenario, rounds)
    return records, _validation(grade), rounds, False


def peak_concurrency(records: Sequence[InvocationRecord]) -> int:
    """Most child invocations that ran at once, from their observed windows."""
    events: list[tuple[float, int]] = []
    for record in records:
        if record.request.role in CHILD_ROLES:
            seen = record.observation
            events.append((seen.start_offset_seconds, 1))
            events.append((seen.start_offset_seconds + seen.elapsed_seconds, -1))
    running = peak = 0
    for _, delta in sorted(events):
        running += delta
        peak = max(peak, running)
    return peak


def _value_violations(records: Sequence[InvocationRecord]) -> list[str]:
    parent = next((r for r in records if r.request.role == "orchestrator"), None)
    problems: list[str] = []
    for record in records:
        seen = record.observation
        ident = record.request.invocation_id
        checks = (
            (
                "model",
                record.model_verdict,
                seen.observed_model,
                parent.observation.observed_model if parent else None,
            ),
            (
                "effort",
                record.effort_verdict,
                seen.observed_effort,
                parent.observation.observed_effort if parent else None,
            ),
        )
        for name, verdict, observed, parent_value in checks:
            if verdict is not Verdict.MISMATCH:
                continue
            inherited = record is not parent and observed is not None and observed == parent_value
            code = f"silent_{name}_inheritance" if inherited else f"{name}_mismatch"
            problems.append(f"{code}:{ident}")
    return problems


def _context_violations(strategy: Strategy, records: Sequence[InvocationRecord]) -> list[str]:
    problems: list[str] = []
    earlier_sessions: set[str] = set()
    for record in records:
        seen = record.observation
        ident = record.request.invocation_id
        if record.request.fresh_context:
            if "fresh_session" not in seen.context_markers:
                problems.append(f"fresh_context_missing:{ident}")
            if seen.session_id in earlier_sessions:
                problems.append(f"fresh_session_reused:{ident}")
        reviewer = strategy.reviewer
        if record.request.role == "reviewer" and reviewer is not None and reviewer.isolated:
            if seen.reviewer_context_leak:
                problems.append(f"reviewer_isolation_broken:{ident}")
        earlier_sessions.add(seen.session_id)
    return problems


def _handoff_violations(records: Sequence[InvocationRecord]) -> list[str]:
    by_id = {record.request.invocation_id: record.observation for record in records}
    if PLAN_INVOCATION_ID not in by_id or IMPLEMENT_INVOCATION_ID not in by_id:
        return []
    produced = by_id[PLAN_INVOCATION_ID].artifact_sha
    consumed = by_id[IMPLEMENT_INVOCATION_ID].consumed_artifact_sha
    if produced is None:
        return ["handoff_missing:planner-plan"]
    if consumed != produced:
        return ["handoff_mismatch:implementer-implement"]
    return []


def _violations(
    strategy: Strategy, records: Sequence[InvocationRecord], rounds: int
) -> tuple[str, ...]:
    problems = _value_violations(records) + _context_violations(strategy, records)
    problems += _handoff_violations(records)
    peak = peak_concurrency(records)
    if peak > strategy.max_concurrency:
        problems.append(f"concurrency_ceiling_exceeded:{peak}>{strategy.max_concurrency}")
    if rounds > strategy.max_correction_rounds:
        problems.append(f"correction_budget_exceeded:{rounds}>{strategy.max_correction_rounds}")
    return tuple(problems)


def _notes(strategy: Strategy, records: Sequence[InvocationRecord]) -> tuple[str, ...]:
    notes: list[str] = []
    for record in records:
        ident = record.request.invocation_id
        seen = record.observation
        if record.model_verdict is Verdict.UNVERIFIED:
            notes.append(f"unverified_model:{ident}")
        if record.effort_verdict is Verdict.UNVERIFIED:
            notes.append(f"unverified_effort:{ident}")
        if seen.input_tokens is None or seen.output_tokens is None:
            notes.append(f"telemetry_unavailable:{ident}")
        reviewer = strategy.reviewer
        if record.request.role == "reviewer" and reviewer and reviewer.isolated:
            if seen.reviewer_context_leak is None:
                notes.append(f"reviewer_isolation_unobserved:{ident}")
    return tuple(notes)


def _status(
    harness_failed: bool,
    violations: Sequence[str],
    records: Sequence[InvocationRecord],
    validation: Validation | None,
) -> RunStatus:
    if harness_failed:
        return RunStatus.HARNESS_FAILED
    if violations:
        return RunStatus.CONTRACT_VIOLATION
    task_failed = any(r.observation.failure is FailureKind.TASK for r in records)
    if task_failed or validation is None or validation.verdict != GradeVerdict.PASS.value:
        return RunStatus.TASK_FAILED
    return RunStatus.ACCEPTED


def _unique(values: Sequence[str | None]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def run_planned(
    row: PlanRow, strategy: Strategy, scenario: Scenario, backend: Backend
) -> RunResult:
    """Execute one `PLANNED` row. Any other status raises before any invocation."""
    if row.status is not RowStatus.PLANNED:
        raise ValueError(
            f"row {row.scenario_id}/{row.arm}/{row.harness} is {row.status.value}: {row.reason}"
        )
    records, validation, rounds, harness_failed = _execute(strategy, scenario, backend)
    violations = _violations(strategy, records, rounds)
    markers = [m for r in records for m in r.observation.context_markers]
    by_id = {r.request.invocation_id: r.observation for r in records}
    planner, implementer = by_id.get(PLAN_INVOCATION_ID), by_id.get(IMPLEMENT_INVOCATION_ID)
    tokens_in = sum_known([r.observation.input_tokens for r in records])
    tokens_out = sum_known([r.observation.output_tokens for r in records])
    return RunResult(
        scenario_id=row.scenario_id,
        arm=row.arm,
        harness=row.harness,
        harness_version=row.harness_version,
        eligibility=row.eligibility,
        comparison=row.comparison.value,
        comparison_reason=row.comparison_reason,
        pair_id=row.pair_id,
        status=_status(harness_failed, violations, records, validation),
        invocations=tuple(records),
        validation=validation,
        correction_rounds=rounds,
        peak_concurrency=peak_concurrency(records),
        violations=violations,
        notes=_notes(strategy, records),
        tool_sandbox=_unique([r.observation.tool_sandbox for r in records]),
        context_markers=_unique(markers),
        telemetry_available=tokens_in is not None and tokens_out is not None,
        total_input_tokens=None if tokens_in is None else int(tokens_in),
        total_output_tokens=None if tokens_out is None else int(tokens_out),
        total_cost_usd=None
        if (cost := sum_known([r.cost_usd for r in records])) is None
        else float(cost),
        plan_artifact_sha=planner.artifact_sha if planner else None,
        plan_deviations=implementer.plan_deviations if implementer else (),
    )


def _difference_reasons(first: RunResult, second: RunResult) -> list[str]:
    reasons: list[str] = []
    if first.peak_concurrency != second.peak_concurrency:
        reasons.append(
            f"concurrency_peak_differs:{first.peak_concurrency}!={second.peak_concurrency}"
        )
    if first.tool_sandbox != second.tool_sandbox:
        reasons.append(
            f"tool_sandbox_differs:{list(first.tool_sandbox)}!={list(second.tool_sandbox)}"
        )
    if first.context_markers != second.context_markers:
        reasons.append("context_markers_differ")
    if _isolation_state(first) != _isolation_state(second):
        reasons.append("reviewer_isolation_differs")
    if (first.plan_artifact_sha is None) != (second.plan_artifact_sha is None):
        reasons.append("plan_artifact_handoff_differs")
    return reasons


def _isolation_state(result: RunResult) -> tuple[bool | None, ...]:
    return tuple(
        record.observation.reviewer_context_leak
        for record in result.invocations
        if record.request.role == "reviewer"
    )


def compare_pair(first: RunResult, second: RunResult) -> PairVerdict:
    """Decide whether two runs of one arm on two harnesses are a matched comparison.

    `INCOMPARABLE`: the runs are not one scenario and arm on two harnesses, or a
    harness failure means the task outcome is unknown.
    `UNMATCHED`: the plan was not matched, a run broke a contract, or an
    observed difference (concurrency, sandbox, context, reviewer isolation,
    handoff) prevents a causal comparison. Reasons name each difference; none
    is normalized away. `UNVERIFIED`: no difference, but a requested model or
    effort has no backend evidence in one run, so parity is not shown.
    `MATCHED`: none of the above.
    """
    telemetry = first.telemetry_available and second.telemetry_available
    if (first.scenario_id, first.arm) != (second.scenario_id, second.arm) or (
        first.harness == second.harness
    ):
        return PairVerdict("INCOMPARABLE", ("not_a_pair_of_harness_runs",), telemetry)
    failed = [r.harness for r in (first, second) if r.status is RunStatus.HARNESS_FAILED]
    if failed:
        return PairVerdict(
            "INCOMPARABLE", tuple(f"harness_failure:{name}" for name in failed), telemetry
        )
    reasons: list[str] = []
    for result in (first, second):
        if result.comparison != HarnessComparison.MATCHED.value:
            reasons.append(f"plan_unmatched:{result.harness}:{result.comparison_reason}")
        reasons += [f"{result.harness}:{code}" for code in result.violations]
    reasons += _difference_reasons(first, second)
    if reasons:
        return PairVerdict("UNMATCHED", tuple(reasons), telemetry)
    unverified = [
        f"{result.harness}:{note}"
        for result in (first, second)
        for note in result.notes
        if note.startswith(("unverified_model", "unverified_effort"))
    ]
    if unverified:
        return PairVerdict("UNVERIFIED", tuple(unverified), telemetry)
    return PairVerdict("MATCHED", (), telemetry)
