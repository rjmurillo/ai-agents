"""Dataclasses and exceptions for eval-agent-vs-baseline runner.

DESIGN-004 §5.2 (Fixture), §5.3 (Assertion + AssertionResult), §5.3a
(ExecutionPlan), §5.5 (RunRecord), §5.6 (Report). All serializable types
carry schemaVersion: 1 (REQ-004 AC-7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

SCHEMA_VERSION: int = 1

# Provenance values per REQ-004 AC-4.
ProvenanceLiteral = Literal["synthetic", "public-cve", "paraphrased-from-public"]
# Issue #1875 (form-factor eval, follow-on to ADR-058) adds the `skill`
# variant: the same domain content the `agent` variant carries in a subagent
# system prompt, delivered instead as a SKILL.md read into the parent's
# context and reasoned over inline in a single model call (no subagent
# dispatch). The three variants let the report compute the three pairwise
# CIs the issue specifies: agent-baseline, skill-baseline, agent-skill.
VariantLiteral = Literal["agent", "baseline", "skill"]
OutcomeLiteral = Literal["success", "error"]
# ADR-058 promotes `halt-due-to-flakiness` to a fourth verdict outcome
# emitted when REQ-004 AC-10's flakiness gate trips. The runtime, the
# report writer, and `tests/evals/test_eval_agent_vs_baseline.py`
# (assert payload["recommendation"] == "halt-due-to-flakiness") already
# use this value; the type literal is the last surface that lagged.
RecommendationLiteral = Literal[
    "graduate-to-CI",
    "keep-as-audit",
    "scrap",
    "halt-due-to-flakiness",
]


class AssertionKind(str, Enum):
    """Kind of assertion. AST and TEST_PASS are deferred (DESIGN-004 §5.3)."""

    REGEX = "regex"
    VERDICT = "verdict"
    # AST = "ast"        # deferred
    # TEST_PASS = "test_pass"  # deferred


class SchemaVersionError(Exception):
    """Raised when a record's schemaVersion is missing or unsupported."""


class FixtureValidationError(Exception):
    """Raised when a fixture fails validation per REQ-004 AC-4."""


@dataclass(frozen=True)
class Assertion:
    """One scoring assertion attached to a fixture.

    Constraint: REGEX kind sets `pattern`; VERDICT kind sets `expected_value`.
    At least one of the two MUST be non-None.
    """

    kind: AssertionKind
    pattern: str | None = None
    expected_value: str | None = None

    def __post_init__(self) -> None:
        # Tighten the contract: REGEX MUST set `pattern` (and only
        # `pattern`); VERDICT MUST set `expected_value` (and only
        # `expected_value`). The previous "at least one is set" rule let
        # mismatched kind/field pairs slip through to the scorer where
        # they produced silent zero-pass results. Validate at the
        # constructor so callers get a typed error before any API call.
        if self.kind is AssertionKind.REGEX:
            if self.pattern is None:
                raise ValueError("REGEX assertions require pattern")
            if self.expected_value is not None:
                raise ValueError(
                    "REGEX assertions must not set expected_value"
                )
            return
        if self.kind is AssertionKind.VERDICT:
            if self.expected_value is None:
                raise ValueError("VERDICT assertions require expected_value")
            if self.pattern is not None:
                raise ValueError(
                    "VERDICT assertions must not set pattern"
                )
            return
        # Defensive fallthrough: AssertionKind is a closed enum, but a
        # future kind added without updating this guard would silently
        # accept malformed assertions.
        raise ValueError(f"unsupported AssertionKind: {self.kind!r}")


@dataclass(frozen=True)
class AssertionResult:
    """Outcome of scoring one assertion against a model response.

    Mirrors the shape of the input Assertion (`pattern`, `expected_value`)
    so downstream serialization preserves which kind was scored.
    """

    kind: AssertionKind
    pattern: str | None
    expected_value: str | None
    passed: bool
    extracted: str | None


@dataclass
class Fixture:
    """One held-out scoring fixture loaded from `evals/security-spike/fixtures/`."""

    id: str
    input: str
    provenance: ProvenanceLiteral
    assertions: list[Assertion]
    tags: list[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION


@dataclass
class RunRecord:
    """One (fixture_id, variant, run_index) result row in `runs.jsonl`.

    DESIGN-004 §5.5. Persistence and idempotency live in T4-2; T4-1 only
    defines the shape so T4-2 can `from _eval_agent_types import RunRecord`.

    `tokens_estimated` defaults to True because the Anthropic API helper
    used by the spike does not surface a `usage` envelope yet; the adapter
    derives token counts from text length. Once `_anthropic_api.call_api`
    returns measured usage, callers will set this False on success records.
    """

    fixture_id: str
    variant: VariantLiteral
    run_index: int
    model_id: str
    prompt_sha: str
    prompt_ref: str
    fixture_sha: str
    raw_response: str | None
    assertions: list[AssertionResult]
    outcome: OutcomeLiteral
    latency_ms: float
    tokens_in: int
    tokens_out: int
    error_category: str | None
    attempts: int
    tokens_estimated: bool = True
    schema_version: int = SCHEMA_VERSION


@dataclass
class Report:
    """Aggregated report per (run_id). DESIGN-004 §5.6.

    `recommendation` is null on T4-5 commits and overwritten in T4-7. The
    JSON schema accepts both shapes; see DESIGN-004 §5.6 schema notes.
    """

    run_id: str
    model_id: str
    agent_prompt_sha: str
    baseline_prompt_sha: str
    fixture_set_sha: str
    agent_recall: float
    baseline_recall: float
    recall_delta: float
    bootstrap_ci_95: tuple[float, float]
    recall_with_errors: float
    recall_excluding_errors: float
    per_fixture_pass_rates: dict[str, dict[str, list[float]]]
    flakiness: bool
    total_tokens_in: int
    total_tokens_out: int
    wall_clock_seconds: float
    cost_estimate_usd: float
    error_count: int
    pricing_rate_as_of: str
    flaky_fixtures_detected: list[str] = field(default_factory=list)
    flaky_fixtures_excluded: list[str] = field(default_factory=list)
    flaky_halt_threshold_crossed: bool = False
    tokens_estimated: bool = True
    recommendation: RecommendationLiteral | None = None
    recommendation_default: str | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class ExecutionPlan:
    """Output of `PlanRunner.build_plan()`. Used by both dry-run and live paths."""

    fixtures: list[Fixture]
    variants: tuple[VariantLiteral, ...]
    n_runs: int
    model_id: str
    planned_calls: int
    estimated_tokens_in: int
    estimated_tokens_out: int
    estimated_cost_usd: float
    pricing_rate_as_of: str
    schema_version: int = SCHEMA_VERSION
