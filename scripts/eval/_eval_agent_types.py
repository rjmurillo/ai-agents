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
VariantLiteral = Literal["agent", "baseline"]
OutcomeLiteral = Literal["success", "error"]
RecommendationLiteral = Literal["graduate-to-CI", "keep-as-audit", "scrap"]


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
        if self.pattern is None and self.expected_value is None:
            raise ValueError(
                "Assertion requires pattern (REGEX) or expected_value (VERDICT)"
            )


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
    flaky_fixtures_excluded: list[str] = field(default_factory=list)
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
