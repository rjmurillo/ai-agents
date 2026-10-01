"""Structured result records for the routing benchmark (issue #5424).

Pure data and small classifiers. Each `RunResult` carries the fields issue
#5424 "Structured result" lists: scenario and arm, harness name and version,
matched-comparison eligibility and reason, session and phase ids, the
invocation order with concurrency windows, requested and observed
model/effort, a tool/sandbox fingerprint, fresh-session and reset markers,
tokens, cost, elapsed time, the deterministic validation evidence, correction
rounds, harness failure kept apart from task failure, and for plan-artifact
flows the artifact hash and deviations.

Fail-closed rules:

* an observed model or effort is `HONORED` only when it comes from `BACKEND`
  evidence and equals the request. A client echo or a missing value is
  `UNVERIFIED`; nothing is inferred (#5423 negative controls 2 and 3);
* a token count or cost the harness did not report stays `None`. It is never
  filled with zero, and a run total is `None` when any part is unknown;
* pricing comes from `_eval_common.MODEL_PRICING_RATES_USD_PER_1K_TOKENS`. A
  model with no rate has no cost, as `_eval_common` documents for the
  GPT-5.6 ids.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from _eval_common import MODEL_PRICING_RATES_USD_PER_1K_TOKENS
from _harness_capability import EvidenceKind

SESSION_MARKER_FRESH = "fresh_session"
CONTEXT_MARKERS = frozenset({SESSION_MARKER_FRESH, "reset", "restart", "compaction"})
CHILD_ROLES = frozenset({"worker", "reviewer"})


class FailureKind(str, Enum):
    """A harness or runtime failure is never counted as a task failure."""

    HARNESS = "harness"
    TASK = "task"


class Verdict(str, Enum):
    """Requested versus observed value for one invocation."""

    HONORED = "HONORED"
    MISMATCH = "MISMATCH"
    UNVERIFIED = "UNVERIFIED"


class RunStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    TASK_FAILED = "TASK_FAILED"
    HARNESS_FAILED = "HARNESS_FAILED"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"


@dataclass(frozen=True, slots=True)
class InvocationRequest:
    invocation_id: str
    phase_id: str
    role: str
    work_package_id: str | None
    difficulty: str | None
    model: str
    effort: str
    depends_on: tuple[str, ...]
    fresh_context: bool
    session_id: str
    correction_round: int = 0


@dataclass(frozen=True, slots=True)
class Observation:
    """What the harness reported for one invocation. `None` means not reported."""

    session_id: str
    start_offset_seconds: float
    elapsed_seconds: float
    observed_model: str | None
    observed_effort: str | None
    evidence: EvidenceKind
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_sandbox: str | None = None
    context_markers: tuple[str, ...] = ()
    failure: FailureKind | None = None
    failure_detail: str = ""
    artifact_sha: str | None = None
    consumed_artifact_sha: str | None = None
    plan_deviations: tuple[str, ...] = ()
    reviewer_context_leak: bool | None = None


@dataclass(frozen=True, slots=True)
class InvocationRecord:
    request: InvocationRequest
    observation: Observation
    model_verdict: Verdict
    effort_verdict: Verdict
    cost_usd: float | None


@dataclass(frozen=True, slots=True)
class Validation:
    """Deterministic grader evidence for one graded round."""

    verdict: str
    changed_paths: tuple[str, ...]
    scope_violations: tuple[str, ...]
    missing_expected: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunResult:
    scenario_id: str
    arm: str
    harness: str
    harness_version: str
    eligibility: str
    comparison: str
    comparison_reason: str
    pair_id: str | None
    status: RunStatus
    invocations: tuple[InvocationRecord, ...]
    validation: Validation | None
    correction_rounds: int
    peak_concurrency: int
    violations: tuple[str, ...]
    notes: tuple[str, ...]
    tool_sandbox: tuple[str, ...]
    context_markers: tuple[str, ...]
    telemetry_available: bool
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_cost_usd: float | None
    plan_artifact_sha: str | None
    plan_deviations: tuple[str, ...]


def value_verdict(requested: str, observed: str | None, evidence: EvidenceKind) -> Verdict:
    """`HONORED` needs backend evidence that equals the request."""
    if observed is None or evidence is not EvidenceKind.BACKEND:
        return Verdict.UNVERIFIED
    return Verdict.HONORED if observed == requested else Verdict.MISMATCH


def estimate_cost_usd(
    model: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """Cost from the in-tree per-1K-token rates, or `None` when any input is unknown."""
    rates = MODEL_PRICING_RATES_USD_PER_1K_TOKENS.get(model)
    if rates is None or input_tokens is None or output_tokens is None:
        return None
    cost: float = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1000
    return cost


def sum_known(values: Sequence[float | int | None]) -> float | int | None:
    """Total of `values`, or `None` when any element is unknown or `values` is empty."""
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _invocation_dict(record: InvocationRecord) -> dict[str, object]:
    request = record.request
    seen = record.observation
    return {
        "invocation_id": request.invocation_id,
        "phase_id": request.phase_id,
        "session_id": seen.session_id,
        "role": request.role,
        "work_package_id": request.work_package_id,
        "difficulty": request.difficulty,
        "depends_on": list(request.depends_on),
        "correction_round": request.correction_round,
        "requested": {"model": request.model, "effort": request.effort},
        "observed": {
            "model": seen.observed_model,
            "effort": seen.observed_effort,
            "evidence": seen.evidence.value,
        },
        "model_verdict": record.model_verdict.value,
        "effort_verdict": record.effort_verdict.value,
        "window": {
            "start": seen.start_offset_seconds,
            "end": seen.start_offset_seconds + seen.elapsed_seconds,
        },
        "elapsed_seconds": seen.elapsed_seconds,
        "input_tokens": seen.input_tokens,
        "output_tokens": seen.output_tokens,
        "cost_usd": record.cost_usd,
        "tool_sandbox": seen.tool_sandbox,
        "context_markers": list(seen.context_markers),
        "fresh_context_requested": request.fresh_context,
        "failure": None
        if seen.failure is None
        else {"kind": seen.failure.value, "detail": seen.failure_detail},
    }


def result_to_dict(result: RunResult) -> dict[str, object]:
    """JSON-ready form. Harness identity and eligibility are always present."""
    validation = result.validation
    return {
        "scenario_id": result.scenario_id,
        "arm": result.arm,
        "harness": {"name": result.harness, "version": result.harness_version},
        "eligibility": result.eligibility,
        "comparison": {
            "class": result.comparison,
            "reason": result.comparison_reason,
            "pair_id": result.pair_id,
        },
        "status": result.status.value,
        "invocations": [_invocation_dict(item) for item in result.invocations],
        "validation": None
        if validation is None
        else {
            "verdict": validation.verdict,
            "changed_paths": list(validation.changed_paths),
            "scope_violations": list(validation.scope_violations),
            "missing_expected": list(validation.missing_expected),
        },
        "correction_rounds": result.correction_rounds,
        "peak_concurrency": result.peak_concurrency,
        "violations": list(result.violations),
        "notes": list(result.notes),
        "tool_sandbox": list(result.tool_sandbox),
        "context_markers": list(result.context_markers),
        "telemetry_available": result.telemetry_available,
        "totals": {
            "input_tokens": result.total_input_tokens,
            "output_tokens": result.total_output_tokens,
            "cost_usd": result.total_cost_usd,
        },
        "plan_artifact": None
        if result.plan_artifact_sha is None
        else {"sha256": result.plan_artifact_sha, "deviations": list(result.plan_deviations)},
    }
