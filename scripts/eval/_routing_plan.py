"""Zero-spend plan for the routing benchmark: strategy x scenario x harness (issue #5424).

`build_plan` makes no model call and starts no subprocess. It expands the
matrix, asks the #5423 capability matrix whether each harness can run each
arm, and classifies every planned pair of harnesses as matched or unmatched
before any spend.

Eligibility authority is `_harness_capability.build_report(records)`. This
module reads its `arm_eligibility` rows and never derives a class itself, so
`UNSUPPORTED` and `UNVERIFIED` combinations are rejected exactly as #5423
classified them. The issue's dependency section: "Use only harness x
model/effort/topology combinations classified `ELIGIBLE_MATCHED` or
`ELIGIBLE_UNMATCHED` there."

Two rules keep a comparison honest (#5424 "Harness comparison contract"):

* a matched harness comparison needs both harnesses `ELIGIBLE_MATCHED` and an
  identical semantic contract, so a config difference in concurrency, reviewer
  isolation, fresh-context boundary, correction budget, model, or effort makes
  the pair `UNMATCHED` with the field named;
* nothing is normalized away: a difference is listed, never dropped.

Stricter than the capability matrix: a requested model or effort must appear
in the record's observed `supported_models` and `supported_efforts`. The
matrix only requires each arm's model families, so a config naming a model the
harness was never seen running is rejected here as `UNVERIFIED`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, cast

from _harness_capability import ArmEligibility, HarnessCapabilityRecord, build_report
from _routing_config import BenchmarkConfig, HarnessRef, ModelEffort, Strategy, Topology
from _routing_grader import fixture_manifest
from _routing_scenario import DifficultyClass, Scenario

_ELIGIBLE = frozenset({ArmEligibility.ELIGIBLE_MATCHED, ArmEligibility.ELIGIBLE_UNMATCHED})


class RowStatus(str, Enum):
    PLANNED = "PLANNED"
    REJECTED = "REJECTED"


class HarnessComparison(str, Enum):
    """How this row relates to the same arm on another harness."""

    MATCHED = "matched"
    UNMATCHED = "unmatched"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Route:
    role: str
    route: ModelEffort


@dataclass(frozen=True, slots=True)
class PlanRow:
    scenario_id: str
    category: str
    difficulty: str
    arm: str
    harness: str
    harness_version: str
    status: RowStatus
    eligibility: str
    reason: str
    routes: tuple[Route, ...]
    comparison: HarnessComparison
    comparison_reason: str
    pair_id: str | None
    within_harness_group: str
    contract_sha: str


@dataclass(frozen=True, slots=True)
class Plan:
    rows: tuple[PlanRow, ...]
    problems: tuple[str, ...]

    @property
    def planned(self) -> tuple[PlanRow, ...]:
        return tuple(row for row in self.rows if row.status is RowStatus.PLANNED)

    @property
    def matched_pairs(self) -> tuple[str, ...]:
        return tuple(sorted({row.pair_id for row in self.planned if row.pair_id}))


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def requested_routes(strategy: Strategy, difficulty: DifficultyClass) -> tuple[Route, ...]:
    """Every model and effort a run of `strategy` on this difficulty class requests."""
    routes = [Route("orchestrator", strategy.orchestrator)]
    if strategy.topology is Topology.FAN_OUT:
        routes.append(Route("worker", strategy.workers[difficulty]))
    if strategy.implementer is not None:
        routes.append(Route("implementer", strategy.implementer))
    if strategy.reviewer is not None:
        routes.append(Route("reviewer", strategy.reviewer.route))
    return tuple(routes)


def semantic_contract(strategy: Strategy, scenario: Scenario) -> dict[str, object]:
    """Everything #5424 holds constant across harnesses for a matched comparison."""
    reviewer = strategy.reviewer
    return {
        "scenario_id": scenario.scenario_id,
        "scenario_state": _sha(fixture_manifest(scenario.fixture_dir("initial"))),
        "task_text": _sha(scenario.requirement),
        "grader": _sha(
            [scenario.validation.commands, fixture_manifest(scenario.fixture_dir("hidden"))]
        ),
        "difficulty": scenario.difficulty.value,
        "routes": [
            [r.role, r.route.model, r.route.effort]
            for r in requested_routes(strategy, scenario.difficulty)
        ],
        "work_packages": strategy.work_packages,
        "max_concurrency": strategy.max_concurrency,
        "max_correction_rounds": strategy.max_correction_rounds,
        "reviewer": None
        if reviewer is None
        else [reviewer.route.model, reviewer.route.effort, reviewer.isolated],
        "fresh_context_boundary": strategy.fresh_context_boundary,
        "handoff_artifact": strategy.handoff_artifact,
    }


def contract_differences(first: Mapping[str, object], second: Mapping[str, object]) -> list[str]:
    """Names of the contract fields that differ between two harnesses."""
    return sorted(key for key in first.keys() | second.keys() if first.get(key) != second.get(key))


def _unsupported_reason(route: Route, record: HarnessCapabilityRecord) -> str | None:
    if route.route.model not in record.supported_models:
        return f"{route.role} model {route.route.model!r} not observed on {record.harness}"
    if route.route.effort not in record.supported_efforts:
        return f"{route.role} effort {route.route.effort!r} not observed on {record.harness}"
    return None


def _first_reason(routes: Sequence[Route], record: HarnessCapabilityRecord) -> str | None:
    for route in routes:
        reason = _unsupported_reason(route, record)
        if reason:
            return reason
    return None


def _eligibility_by_arm(records: Sequence[HarnessCapabilityRecord]) -> dict[str, dict[str, str]]:
    rows = cast("list[dict[str, Any]]", build_report(records)["arm_eligibility"])
    return {str(row["arm"]): dict(row["eligibility"]) for row in rows}


def _row(
    scenario: Scenario,
    strategy: Strategy,
    ref: HarnessRef,
    status: RowStatus,
    eligibility: str,
    reason: str,
) -> PlanRow:
    contract = semantic_contract(strategy, scenario)
    return PlanRow(
        scenario_id=scenario.scenario_id,
        category=scenario.category.value,
        difficulty=scenario.difficulty.value,
        arm=strategy.arm,
        harness=ref.harness,
        harness_version=ref.version,
        status=status,
        eligibility=eligibility,
        reason=reason,
        routes=requested_routes(strategy, scenario.difficulty),
        comparison=HarnessComparison.NONE,
        comparison_reason="",
        pair_id=None,
        within_harness_group=f"{scenario.scenario_id}:{ref.harness}",
        contract_sha=_sha(contract),
    )


def _classify(
    scenario: Scenario,
    strategy: Strategy,
    ref: HarnessRef,
    record: HarnessCapabilityRecord | None,
    eligibility: Mapping[str, str],
) -> PlanRow:
    def reject(kind: ArmEligibility, reason: str) -> PlanRow:
        return _row(scenario, strategy, ref, RowStatus.REJECTED, kind.value, reason)

    if record is None:
        return reject(
            ArmEligibility.UNSUPPORTED, "harness is not classified by the capability matrix"
        )
    if record.version != ref.version:
        return reject(
            ArmEligibility.UNVERIFIED,
            f"config version {ref.version!r} differs from matrix version {record.version!r}",
        )
    verdict = ArmEligibility(eligibility.get(ref.harness, ArmEligibility.UNVERIFIED.value))
    if verdict not in _ELIGIBLE:
        return reject(
            verdict, f"capability matrix classifies arm {strategy.arm} as {verdict.value}"
        )
    reason = _first_reason(requested_routes(strategy, scenario.difficulty), record)
    if reason:
        return reject(ArmEligibility.UNVERIFIED, reason)
    return _row(scenario, strategy, ref, RowStatus.PLANNED, verdict.value, "eligible")


def _with_comparison(
    row: PlanRow, comparison: HarnessComparison, reason: str, pair: str | None
) -> PlanRow:
    return replace(row, comparison=comparison, comparison_reason=reason, pair_id=pair)


def _classify_group(
    rows: list[PlanRow], contracts: Mapping[str, Mapping[str, object]]
) -> list[PlanRow]:
    """Mark the planned rows of one (scenario, arm) as matched or unmatched."""
    if len(rows) < 2:
        return [
            _with_comparison(row, HarnessComparison.NONE, "only one harness is planned", None)
            for row in rows
        ]
    reasons: list[str] = []
    first = rows[0]
    for other in rows[1:]:
        diffs = contract_differences(contracts[first.harness], contracts[other.harness])
        if diffs:
            reasons.append(f"{first.harness} vs {other.harness} differ in {', '.join(diffs)}")
    if any(row.eligibility != ArmEligibility.ELIGIBLE_MATCHED.value for row in rows):
        reasons.append("capability matrix classifies a harness ELIGIBLE_UNMATCHED")
    if reasons:
        return [
            _with_comparison(row, HarnessComparison.UNMATCHED, "; ".join(reasons), None)
            for row in rows
        ]
    pair = f"{first.scenario_id}:{first.arm}"
    return [
        _with_comparison(row, HarnessComparison.MATCHED, "same semantic contract", pair)
        for row in rows
    ]


def build_plan(
    config: BenchmarkConfig,
    records: Sequence[HarnessCapabilityRecord],
    scenarios: Sequence[Scenario],
) -> Plan:
    """Expand strategy x scenario x harness with zero model calls."""
    by_harness = {record.harness: record for record in records}
    eligibility = _eligibility_by_arm(records)
    problems = tuple(
        f"harness {ref.harness!r} is not classified by the capability matrix"
        for ref in config.harnesses
        if ref.harness not in by_harness
    )
    rows: list[PlanRow] = []
    for scenario in scenarios:
        for strategy in config.strategies:
            group: list[PlanRow] = []
            contracts: dict[str, Mapping[str, object]] = {}
            for ref in config.harnesses:
                resolved = config.strategy_for(strategy.arm, ref.harness)
                row = _classify(
                    scenario,
                    resolved,
                    ref,
                    by_harness.get(ref.harness),
                    eligibility.get(strategy.arm, {}),
                )
                contracts[ref.harness] = semantic_contract(resolved, scenario)
                (group if row.status is RowStatus.PLANNED else rows).append(row)
            rows.extend(_classify_group(group, contracts))
    return Plan(tuple(rows), problems)
