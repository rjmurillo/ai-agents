"""Durable outcome record contract and strict parser (REQ-042 AC-1, DESIGN-040).

Pure, stdlib only. One `OutcomeRecord` is one task run under one `RunConfig`,
with capability, execution, durable, economics, and risk sections.
`parse_record` refuses unknown keys, missing required keys, bad enum values,
negative numbers, and `bool` where an `int` is required (Python's `bool` is
an `int` subclass, so `isinstance(x, int)` alone would accept `True` as 1).

Fail-closed, like `_harness_capability.py::CapabilityStatus`: missing
evidence is `UNVERIFIED`, never `PASS`. The classifier, report, and matched
comparison live in `_durable_outcome.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Errors and enums
# ---------------------------------------------------------------------------


class DurableOutcomeError(ValueError):
    """A record, report, or comparison request is invalid.

    Raised instead of degrading to a permissive default, so every refusal in
    this module (unknown key, bad enum, mismatched config, mismatched task
    set) is this one exception type with a message naming the field.
    """


class Evidence(str, Enum):
    """One task-run observation: `PASS`, `FAIL`, or `UNVERIFIED`.

    Missing evidence is `UNVERIFIED`, never `PASS` (REQ-042 ontology).
    """

    PASS = "PASS"
    FAIL = "FAIL"
    UNVERIFIED = "UNVERIFIED"



# ---------------------------------------------------------------------------
# Record shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunConfig:
    """Identity of the configuration a task ran under (REQ-042 ontology).

    Two records are matched when every field except `control` is equal.
    """

    model: str
    harness: str
    harness_version: str
    context_bytes: int
    retry_budget: int
    reviewer: str
    control: str


@dataclass(frozen=True, slots=True)
class Capability:
    attempted: bool
    produced_artifact: bool


@dataclass(frozen=True, slots=True)
class Execution:
    deterministic_acceptance: Evidence
    first_pass: Evidence
    tool_failures: int
    retries: int
    scope_violations: int
    judge: Evidence | None


@dataclass(frozen=True, slots=True)
class Durable:
    followup_validation: Evidence
    objective_satisfied: Evidence
    residual_defects: int | None
    review_findings: int | None
    rollback_events: int | None
    rework_minutes: float | None


@dataclass(frozen=True, slots=True)
class Economics:
    model_cost_usd: float
    tool_cost_usd: float
    wall_seconds: float
    human_correction_minutes: float


@dataclass(frozen=True, slots=True)
class Risk:
    security_findings: int | None
    unapproved_external_actions: int | None
    unsupported_claims: int | None
    unresolved_uncertainty: int | None


@dataclass(frozen=True, slots=True)
class OutcomeRecord:
    """One task run under one `RunConfig` (REQ-042 ontology)."""

    task_id: str
    repeat: int
    config: RunConfig
    capability: Capability
    execution: Execution
    durable: Durable
    economics: Economics
    risk: Risk


_EVIDENCE_VALUES = frozenset(item.value for item in Evidence)

_CONFIG_KEYS = frozenset(
    {"model", "harness", "harness_version", "context_bytes", "retry_budget", "reviewer", "control"}
)
_CAPABILITY_KEYS = frozenset({"attempted", "produced_artifact"})
_EXECUTION_REQUIRED_KEYS = frozenset(
    {"deterministic_acceptance", "first_pass", "tool_failures", "retries", "scope_violations"}
)
_EXECUTION_OPTIONAL_KEYS = frozenset({"judge"})
_DURABLE_KEYS = frozenset(
    {
        "followup_validation",
        "objective_satisfied",
        "residual_defects",
        "review_findings",
        "rollback_events",
        "rework_minutes",
    }
)
_ECONOMICS_KEYS = frozenset(
    {"model_cost_usd", "tool_cost_usd", "wall_seconds", "human_correction_minutes"}
)
_RISK_KEYS = frozenset(
    {
        "security_findings",
        "unapproved_external_actions",
        "unsupported_claims",
        "unresolved_uncertainty",
    }
)
_RECORD_REQUIRED_KEYS = frozenset(
    {"task_id", "repeat", "config", "capability", "execution", "durable", "economics", "risk"}
)


# ---------------------------------------------------------------------------
# Field-level validation helpers
# ---------------------------------------------------------------------------


def _require_dict(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DurableOutcomeError(f"{path}: expected an object, got {type(value).__name__}")
    return value


def _require_keys(data: dict[str, object], required: frozenset[str], path: str) -> None:
    missing = required - data.keys()
    if missing:
        raise DurableOutcomeError(f"{path}: missing required key(s) {sorted(missing)}")
    unknown = data.keys() - required
    if unknown:
        raise DurableOutcomeError(f"{path}: unknown key(s) {sorted(unknown)}")


def _require_keys_with_optional(
    data: dict[str, object], required: frozenset[str], optional: frozenset[str], path: str
) -> None:
    missing = required - data.keys()
    if missing:
        raise DurableOutcomeError(f"{path}: missing required key(s) {sorted(missing)}")
    unknown = data.keys() - required - optional
    if unknown:
        raise DurableOutcomeError(f"{path}: unknown key(s) {sorted(unknown)}")


def _require_nonempty_str(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise DurableOutcomeError(f"{path}: expected a non-empty string, got {value!r}")
    return value


def _require_bool(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise DurableOutcomeError(f"{path}: expected a bool, got {type(value).__name__}")
    return value


def _require_nonneg_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DurableOutcomeError(f"{path}: expected a non-negative int, got {value!r}")
    if value < 0:
        raise DurableOutcomeError(f"{path}: expected a non-negative int, got {value!r}")
    return value


def _require_nonneg_int_or_none(value: object, path: str) -> int | None:
    if value is None:
        return None
    return _require_nonneg_int(value, path)


def _require_nonneg_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DurableOutcomeError(f"{path}: expected a non-negative number, got {value!r}")
    if value < 0:
        raise DurableOutcomeError(f"{path}: expected a non-negative number, got {value!r}")
    return float(value)


def _require_nonneg_number_or_none(value: object, path: str) -> float | None:
    if value is None:
        return None
    return _require_nonneg_number(value, path)


def _require_evidence(value: object, path: str) -> Evidence:
    if not isinstance(value, str) or value not in _EVIDENCE_VALUES:
        raise DurableOutcomeError(
            f"{path}: expected one of {sorted(_EVIDENCE_VALUES)}, got {value!r}"
        )
    return Evidence(value)


def _require_evidence_or_none(value: object, path: str) -> Evidence | None:
    if value is None:
        return None
    return _require_evidence(value, path)


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _parse_config(data: object, path: str) -> RunConfig:
    section = _require_dict(data, path)
    _require_keys(section, _CONFIG_KEYS, path)
    return RunConfig(
        model=_require_nonempty_str(section["model"], f"{path}.model"),
        harness=_require_nonempty_str(section["harness"], f"{path}.harness"),
        harness_version=_require_nonempty_str(
            section["harness_version"], f"{path}.harness_version"
        ),
        context_bytes=_require_nonneg_int(section["context_bytes"], f"{path}.context_bytes"),
        retry_budget=_require_nonneg_int(section["retry_budget"], f"{path}.retry_budget"),
        reviewer=_require_nonempty_str(section["reviewer"], f"{path}.reviewer"),
        control=_require_nonempty_str(section["control"], f"{path}.control"),
    )


def _parse_capability(data: object, path: str) -> Capability:
    section = _require_dict(data, path)
    _require_keys(section, _CAPABILITY_KEYS, path)
    return Capability(
        attempted=_require_bool(section["attempted"], f"{path}.attempted"),
        produced_artifact=_require_bool(section["produced_artifact"], f"{path}.produced_artifact"),
    )


def _parse_execution(data: object, path: str) -> Execution:
    section = _require_dict(data, path)
    _require_keys_with_optional(
        section, _EXECUTION_REQUIRED_KEYS, _EXECUTION_OPTIONAL_KEYS, path
    )
    return Execution(
        deterministic_acceptance=_require_evidence(
            section["deterministic_acceptance"], f"{path}.deterministic_acceptance"
        ),
        first_pass=_require_evidence(section["first_pass"], f"{path}.first_pass"),
        tool_failures=_require_nonneg_int(section["tool_failures"], f"{path}.tool_failures"),
        retries=_require_nonneg_int(section["retries"], f"{path}.retries"),
        scope_violations=_require_nonneg_int(
            section["scope_violations"], f"{path}.scope_violations"
        ),
        judge=_require_evidence_or_none(section.get("judge"), f"{path}.judge"),
    )


def _parse_durable(data: object, path: str) -> Durable:
    section = _require_dict(data, path)
    _require_keys(section, _DURABLE_KEYS, path)
    return Durable(
        followup_validation=_require_evidence(
            section["followup_validation"], f"{path}.followup_validation"
        ),
        objective_satisfied=_require_evidence(
            section["objective_satisfied"], f"{path}.objective_satisfied"
        ),
        residual_defects=_require_nonneg_int_or_none(
            section["residual_defects"], f"{path}.residual_defects"
        ),
        review_findings=_require_nonneg_int_or_none(
            section["review_findings"], f"{path}.review_findings"
        ),
        rollback_events=_require_nonneg_int_or_none(
            section["rollback_events"], f"{path}.rollback_events"
        ),
        rework_minutes=_require_nonneg_number_or_none(
            section["rework_minutes"], f"{path}.rework_minutes"
        ),
    )


def _parse_economics(data: object, path: str) -> Economics:
    section = _require_dict(data, path)
    _require_keys(section, _ECONOMICS_KEYS, path)
    return Economics(
        model_cost_usd=_require_nonneg_number(section["model_cost_usd"], f"{path}.model_cost_usd"),
        tool_cost_usd=_require_nonneg_number(section["tool_cost_usd"], f"{path}.tool_cost_usd"),
        wall_seconds=_require_nonneg_number(section["wall_seconds"], f"{path}.wall_seconds"),
        human_correction_minutes=_require_nonneg_number(
            section["human_correction_minutes"], f"{path}.human_correction_minutes"
        ),
    )


def _parse_risk(data: object, path: str) -> Risk:
    section = _require_dict(data, path)
    _require_keys(section, _RISK_KEYS, path)
    return Risk(
        security_findings=_require_nonneg_int_or_none(
            section["security_findings"], f"{path}.security_findings"
        ),
        unapproved_external_actions=_require_nonneg_int_or_none(
            section["unapproved_external_actions"], f"{path}.unapproved_external_actions"
        ),
        unsupported_claims=_require_nonneg_int_or_none(
            section["unsupported_claims"], f"{path}.unsupported_claims"
        ),
        unresolved_uncertainty=_require_nonneg_int_or_none(
            section["unresolved_uncertainty"], f"{path}.unresolved_uncertainty"
        ),
    )


def parse_record(data: object) -> OutcomeRecord:
    """Parse and strictly validate one OutcomeRecord (REQ-042 AC-1).

    Refuses unknown keys at every level, missing required keys, bad enum
    values, negative numbers, wrong types, and `bool` where an `int` is
    required. `execution.judge` is the sole optional key (DESIGN-040: "judge
    is optional and may be null").
    """
    record = _require_dict(data, "record")
    _require_keys(record, _RECORD_REQUIRED_KEYS, "record")
    return OutcomeRecord(
        task_id=_require_nonempty_str(record["task_id"], "record.task_id"),
        repeat=_require_nonneg_int(record["repeat"], "record.repeat"),
        config=_parse_config(record["config"], "record.config"),
        capability=_parse_capability(record["capability"], "record.capability"),
        execution=_parse_execution(record["execution"], "record.execution"),
        durable=_parse_durable(record["durable"], "record.durable"),
        economics=_parse_economics(record["economics"], "record.economics"),
        risk=_parse_risk(record["risk"], "record.risk"),
    )
