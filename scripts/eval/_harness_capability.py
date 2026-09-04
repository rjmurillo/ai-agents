# taste-lint: ignore file-size. Just over the 500-line ceiling, and fewer than half
# those lines are code: the rest are the per-negative-control rationale issue #5423
# requires every capability cell and classifier to carry. Splitting the parser away
# from the record it validates would route the fail-closed contract, every VERIFIED
# path through HarnessCapabilityError, across an import seam. That contract is the
# property this file exists to keep checkable in one place.
"""Per-harness capability matrix for the #5422 orchestration experiment.

This module is a *capability probe*, not a benchmark (issue #5423). It records,
per harness, whether a runtime control is `VERIFIED`, `UNSUPPORTED`, or
`UNVERIFIED`, and derives whether a Codex-vs-Copilot comparison for each #5422
arm is matched. It changes no defaults, adds no provider, and pins no model.

Authority boundary (do not fork): the transport registry
`scripts/eval/_providers.py::_REGISTRY` and the pricing registry
`scripts/eval/_eval_common.py::MODEL_PRICING_RATES_USD_PER_1K_TOKENS`
(as of `PRICING_RATE_AS_OF`) remain the single source of truth for providers,
models, and pricing. This module records *capability evidence* only and never
copies those tables. `supported_models` here is the set observed live during a
probe, not a model registry.

Fail-closed contract (the point of #5423): a status of `VERIFIED` is only ever
produced from backend runtime evidence. Configuration echo, a matching model
label, a missing runtime version, or malformed metadata can never yield
`VERIFIED`; they raise `HarnessCapabilityError` or resolve to `UNVERIFIED`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

SCHEMA_VERSION = 1


class HarnessCapabilityError(ValueError):
    """The capability matrix document or a record is invalid.

    Raised instead of degrading to a permissive default. Negative control 7
    (malformed metadata fails closed) depends on every parse and validation
    path routing through this exception rather than returning a fallback.
    """


class CapabilityStatus(str, Enum):
    """Per-capability verification state (issue #5423 "Capability record")."""

    VERIFIED = "VERIFIED"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIED = "UNVERIFIED"


class EvidenceKind(str, Enum):
    """Where a capability claim comes from.

    Only `BACKEND` evidence (resolved model id, backend transcript, runtime
    event stream) can support `VERIFIED`. `CLIENT_ECHO` is the request or
    config reflected back; `CONFIG` is a static registry value; `NONE` is no
    evidence at all. Negative control 2 (client/schema echo is not backend
    evidence) is enforced by refusing `VERIFIED` for any non-`BACKEND` kind.
    """

    BACKEND = "backend"
    CLIENT_ECHO = "client_echo"
    CONFIG = "config"
    NONE = "none"


class ArmEligibility(str, Enum):
    """Matched-comparison eligibility for one harness against a peer (#5423)."""

    ELIGIBLE_MATCHED = "ELIGIBLE_MATCHED"
    ELIGIBLE_UNMATCHED = "ELIGIBLE_UNMATCHED"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIED = "UNVERIFIED"


CAPABILITY_KEYS: tuple[str, ...] = (
    "model_override",
    "effort_override",
    "subagent_support",
    "concurrency_limit",
    "parent_child_override",
    "reviewer_isolation",
    "single_agent",
    "fresh_session",
    "durable_artifact_handoff",
    "context_reset_observability",
    "sol_ultra",
)


@dataclass(frozen=True, slots=True)
class Capability:
    """One capability cell: status, where the evidence came from, and detail.

    `value` carries a scalar measurement where a capability has one (the
    verified maximum concurrency for `concurrency_limit`); it is `None`
    otherwise.
    """

    status: CapabilityStatus
    evidence: EvidenceKind
    detail: str = ""
    value: int | None = None


@dataclass(frozen=True, slots=True)
class HarnessCapabilityRecord:
    """A machine-readable capability record for one harness (issue #5423)."""

    harness: str
    version: str
    version_evidence: EvidenceKind
    supported_models: tuple[str, ...]
    supported_efforts: tuple[str, ...]
    capabilities: Mapping[str, Capability]
    tool_sandbox_constraints: str
    telemetry_fields: tuple[str, ...]
    failure_retry_behavior: str
    probe_command: str
    date: str


@dataclass(frozen=True, slots=True)
class Arm:
    """A #5422 competing-hypothesis arm and the capabilities it requires."""

    arm_id: str
    summary: str
    required: tuple[str, ...]
    match_values: tuple[str, ...]


# The six #5422 arms A-F, quoted from issue #5422 "Competing hypotheses" and
# read on 2026-08-31. `match_values` names capability cells whose scalar value
# must be equal across two harnesses for a matched comparison, because the
# #5422 "Fairness contract" holds maximum concurrency constant for the direct
# worker comparisons (arms A-D).
ARMS: tuple[Arm, ...] = (
    Arm(
        "A",
        "Sol fan-out: Sol medium parent, <=3 concurrent Sol low/medium "
        "children, parent integrates and verifies.",
        (
            "model_override",
            "effort_override",
            "subagent_support",
            "concurrency_limit",
            "parent_child_override",
        ),
        ("concurrency_limit",),
    ),
    Arm(
        "B",
        "Heterogeneous routing: Sol orchestrator, <=3 Luna/Terra workers, "
        "Sol review and integration with an isolated reviewer.",
        (
            "model_override",
            "subagent_support",
            "concurrency_limit",
            "parent_child_override",
            "reviewer_isolation",
        ),
        ("concurrency_limit",),
    ),
    Arm(
        "C",
        "Luna high worker isolation: Arm A topology with Sol low replaced by "
        "Luna high for identical bounded work.",
        (
            "model_override",
            "effort_override",
            "subagent_support",
            "concurrency_limit",
            "parent_child_override",
        ),
        ("concurrency_limit",),
    ),
    Arm(
        "D",
        "Terra high worker/fallback: hold parent and topology, test Terra "
        "high on bounded and pre-classified fallback work.",
        (
            "model_override",
            "effort_override",
            "subagent_support",
            "concurrency_limit",
            "parent_child_override",
        ),
        ("concurrency_limit",),
    ),
    Arm(
        "E",
        "Single-agent deep-reasoning Sol: one Sol configuration, no "
        "implementation subagents.",
        (
            "model_override",
            "effort_override",
            "single_agent",
        ),
        (),
    ),
    Arm(
        "F",
        "Durable plan then fresh single Sol: planning subagents finalize "
        "implementation-plan.md, a fresh single-agent context executes it.",
        (
            "subagent_support",
            "durable_artifact_handoff",
            "fresh_session",
            "single_agent",
        ),
        (),
    ),
)


def classify_override(
    requested: str,
    observed: str | None,
    evidence: EvidenceKind,
    *,
    parent_value: str | None = None,
) -> CapabilityStatus:
    """Verify a requested model or effort was honored by the backend.

    Enforces three negative controls at once:
      * control 2: non-`BACKEND` evidence (an echo of the request or config)
        never verifies;
      * control 3/5: an observed value that silently inherited `parent_value`
        while a different value was requested never verifies;
      * a backend value that simply does not equal the request never verifies.

    Returns `VERIFIED` only when the backend reported exactly the requested
    value and did not fall back to the parent. Returns `UNVERIFIED` otherwise.
    Callers that know the harness rejects a control outright record
    `UNSUPPORTED` directly; this helper never invents `UNSUPPORTED`.
    """
    if evidence is not EvidenceKind.BACKEND:
        return CapabilityStatus.UNVERIFIED
    if not observed:
        return CapabilityStatus.UNVERIFIED
    if parent_value is not None and observed == parent_value and requested != parent_value:
        return CapabilityStatus.UNVERIFIED
    if observed != requested:
        return CapabilityStatus.UNVERIFIED
    return CapabilityStatus.VERIFIED


def classify_reviewer_isolation(
    reviewer_context: str,
    producer_private: Sequence[str],
    evidence: EvidenceKind,
) -> CapabilityStatus:
    """Verify a reviewer did not receive producer-private context.

    Negative control 6: claimed reviewer isolation must fail if the reviewer
    receives producer-private context. Returns `VERIFIED` only when the
    evidence is backend and no private token appears in the reviewer context.
    """
    if evidence is not EvidenceKind.BACKEND:
        return CapabilityStatus.UNVERIFIED
    for token in producer_private:
        if token and token in reviewer_context:
            return CapabilityStatus.UNVERIFIED
    return CapabilityStatus.VERIFIED


def derive_arm_eligibility(
    arm: Arm,
    harness: HarnessCapabilityRecord,
    peer: HarnessCapabilityRecord,
) -> ArmEligibility:
    """Classify one harness for one arm relative to a peer harness.

    Precedence (issue #5423 "Matched-comparison eligibility"):
      1. any required capability `UNSUPPORTED` in either harness -> UNSUPPORTED;
      2. any required capability `UNVERIFIED` in either harness -> UNVERIFIED;
      3. all required capabilities `VERIFIED` in both, but a `match_values`
         scalar differs -> ELIGIBLE_UNMATCHED (a material harness difference
         blocks causal comparison);
      4. otherwise -> ELIGIBLE_MATCHED.

    A matched result is reachable only through step 4, which requires backend
    `VERIFIED` on both sides. There is no path that reads a model label, so
    negative control 8 (never infer parity from a matching model label) holds
    structurally: two harnesses reporting the same model but an `UNVERIFIED`
    required capability resolve to `UNVERIFIED`, not matched.
    """
    statuses = [harness.capabilities[key].status for key in arm.required]
    statuses += [peer.capabilities[key].status for key in arm.required]
    if CapabilityStatus.UNSUPPORTED in statuses:
        return ArmEligibility.UNSUPPORTED
    if CapabilityStatus.UNVERIFIED in statuses:
        return ArmEligibility.UNVERIFIED
    for key in arm.match_values:
        if harness.capabilities[key].value != peer.capabilities[key].value:
            return ArmEligibility.ELIGIBLE_UNMATCHED
    return ArmEligibility.ELIGIBLE_MATCHED


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise HarnessCapabilityError(f"{field} must be an object")
    return value


def _string(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise HarnessCapabilityError(f"{field} must be a non-empty string")
    return value


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise HarnessCapabilityError(f"{field} must be an array of strings")
    return tuple(value)


def _enum(enum: type[Enum], value: object, field: str) -> Enum:
    try:
        return enum(value)
    except ValueError as exc:
        raise HarnessCapabilityError(f"{field} is not a valid {enum.__name__}") from exc


def _load_capability(value: object, field: str) -> Capability:
    raw = _mapping(value, field)
    status = _enum(CapabilityStatus, raw.get("status"), f"{field}.status")
    evidence = _enum(EvidenceKind, raw.get("evidence"), f"{field}.evidence")
    detail = _string(raw.get("detail", ""), f"{field}.detail", allow_empty=True)
    scalar = raw.get("value")
    if scalar is not None and (isinstance(scalar, bool) or not isinstance(scalar, int)):
        raise HarnessCapabilityError(f"{field}.value must be an integer or null")
    return Capability(
        status=CapabilityStatus(status),
        evidence=EvidenceKind(evidence),
        detail=detail,
        value=scalar,
    )


def _load_record(value: object, index: int) -> HarnessCapabilityRecord:
    field = f"harnesses[{index}]"
    raw = _mapping(value, field)
    capabilities_raw = _mapping(raw.get("capabilities"), f"{field}.capabilities")
    missing = [key for key in CAPABILITY_KEYS if key not in capabilities_raw]
    if missing:
        raise HarnessCapabilityError(f"{field}.capabilities is missing keys: {missing}")
    unknown = [key for key in capabilities_raw if key not in CAPABILITY_KEYS]
    if unknown:
        raise HarnessCapabilityError(f"{field}.capabilities has unknown keys: {unknown}")
    capabilities = {
        key: _load_capability(capabilities_raw[key], f"{field}.capabilities.{key}")
        for key in CAPABILITY_KEYS
    }
    record = HarnessCapabilityRecord(
        harness=_string(raw.get("harness"), f"{field}.harness"),
        version=_string(raw.get("version", ""), f"{field}.version", allow_empty=True),
        version_evidence=EvidenceKind(
            _enum(EvidenceKind, raw.get("version_evidence"), f"{field}.version_evidence")
        ),
        supported_models=_string_tuple(
            raw.get("supported_models", []), f"{field}.supported_models"
        ),
        supported_efforts=_string_tuple(
            raw.get("supported_efforts", []), f"{field}.supported_efforts"
        ),
        capabilities=capabilities,
        tool_sandbox_constraints=_string(
            raw.get("tool_sandbox_constraints", ""),
            f"{field}.tool_sandbox_constraints",
            allow_empty=True,
        ),
        telemetry_fields=_string_tuple(
            raw.get("telemetry_fields", []), f"{field}.telemetry_fields"
        ),
        failure_retry_behavior=_string(
            raw.get("failure_retry_behavior", ""),
            f"{field}.failure_retry_behavior",
            allow_empty=True,
        ),
        probe_command=_string(
            raw.get("probe_command", ""), f"{field}.probe_command", allow_empty=True
        ),
        date=_string(raw.get("date"), f"{field}.date"),
    )
    validate_record(record)
    return record


def validate_record(record: HarnessCapabilityRecord) -> None:
    """Fail closed on any record that would let a label masquerade as evidence.

    Raises `HarnessCapabilityError` when:
      * control 1: the runtime version is empty but a capability is `VERIFIED`
        (missing runtime identity cannot become verified);
      * control 2: a `VERIFIED` capability is not backed by `BACKEND` evidence;
      * `concurrency_limit` is `VERIFIED` without a positive integer value;
      * control 4: `sol_ultra` is `VERIFIED` without a detail naming the exact
        selectable control (an alias with no direct evidence is refused).
    """
    if not record.harness:
        raise HarnessCapabilityError("record harness must be non-empty")
    has_identity = bool(record.version) and record.version_evidence is EvidenceKind.BACKEND
    for key, capability in record.capabilities.items():
        verified = capability.status is CapabilityStatus.VERIFIED
        if verified and capability.evidence is not EvidenceKind.BACKEND:
            raise HarnessCapabilityError(
                f"{record.harness}.{key} is VERIFIED without backend evidence"
            )
        if verified and not has_identity:
            raise HarnessCapabilityError(
                f"{record.harness}.{key} is VERIFIED without a backend runtime version"
            )
    concurrency = record.capabilities["concurrency_limit"]
    if concurrency.status is CapabilityStatus.VERIFIED and (
        concurrency.value is None or concurrency.value < 1
    ):
        raise HarnessCapabilityError(
            f"{record.harness}.concurrency_limit is VERIFIED without a positive value"
        )
    sol_ultra = record.capabilities["sol_ultra"]
    if sol_ultra.status is CapabilityStatus.VERIFIED and not sol_ultra.detail.strip():
        raise HarnessCapabilityError(
            f"{record.harness}.sol_ultra is VERIFIED without naming its exact control"
        )


def load_matrix(path: Path) -> list[HarnessCapabilityRecord]:
    """Load and validate a capability matrix document, failing closed."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessCapabilityError(f"could not read matrix: {exc}") from exc
    root = _mapping(payload, "matrix document")
    if root.get("schema_version") != SCHEMA_VERSION:
        raise HarnessCapabilityError(f"schema_version must be {SCHEMA_VERSION}")
    raw_records = root.get("harnesses")
    if not isinstance(raw_records, list) or not raw_records:
        raise HarnessCapabilityError("harnesses must be a non-empty array")
    records: list[HarnessCapabilityRecord] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_records):
        record = _load_record(value, index)
        if record.harness in seen:
            raise HarnessCapabilityError(f"duplicate harness: {record.harness}")
        seen.add(record.harness)
        records.append(record)
    return records


def apply_version_probe(
    record: HarnessCapabilityRecord, version: str
) -> HarnessCapabilityRecord:
    """Return a record whose runtime version came from a live backend probe.

    The probe reads `<cli> --version`, so the version alone is `BACKEND`
    evidence of runtime identity. It does not flip any behavioral capability to
    `VERIFIED`; those require live behavioral probes this module does not run.
    """
    return replace(record, version=version, version_evidence=EvidenceKind.BACKEND)


def _capability_dict(capability: Capability) -> dict[str, object]:
    return {
        "status": capability.status.value,
        "evidence": capability.evidence.value,
        "detail": capability.detail,
        "value": capability.value,
    }


def _record_dict(record: HarnessCapabilityRecord) -> dict[str, object]:
    return {
        "harness": record.harness,
        "version": record.version,
        "version_evidence": record.version_evidence.value,
        "supported_models": list(record.supported_models),
        "supported_efforts": list(record.supported_efforts),
        "capabilities": {
            key: _capability_dict(record.capabilities[key]) for key in CAPABILITY_KEYS
        },
        "tool_sandbox_constraints": record.tool_sandbox_constraints,
        "telemetry_fields": list(record.telemetry_fields),
        "failure_retry_behavior": record.failure_retry_behavior,
        "probe_command": record.probe_command,
        "date": record.date,
    }


def _arm_eligibility_dict(
    records: Sequence[HarnessCapabilityRecord],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for arm in ARMS:
        eligibility: dict[str, str] = {}
        for harness in records:
            peers = [peer for peer in records if peer.harness != harness.harness]
            if not peers:
                eligibility[harness.harness] = ArmEligibility.UNVERIFIED.value
                continue
            verdict = derive_arm_eligibility(arm, harness, peers[0])
            eligibility[harness.harness] = verdict.value
        rows.append(
            {"arm": arm.arm_id, "summary": arm.summary, "eligibility": eligibility}
        )
    return rows


def build_report(records: Sequence[HarnessCapabilityRecord]) -> dict[str, object]:
    """Assemble the machine-readable report consumed by #5424 and #5426."""
    return {
        "schema_version": SCHEMA_VERSION,
        "harnesses": [_record_dict(record) for record in records],
        "arm_eligibility": _arm_eligibility_dict(records),
    }
