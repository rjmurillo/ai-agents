"""Benchmark configuration and the A-F strategy invariants (issue #5424).

Pure parsing and validation. No model calls, no subprocesses. One config file
expresses the six #5422 strategy arms and the harness dimension, so a new
model, effort, concurrency ceiling, or reviewer needs no code change.

Authority boundary: provider, model, and pricing registries stay in
`scripts/eval/_providers.py` and `scripts/eval/_eval_common.py`. This module
records the model id a strategy requests and never copies those tables. Whether
a harness can run a requested model is decided in `_routing_plan.py` from the
#5423 capability matrix, which is the eligibility authority.

Arm invariants restate the strategy arms of issue #5424 "Supported strategy
arms" (read 2026-09-29):

    A: Sol medium parent with Sol low/medium children by difficulty
    B: heterogeneous orchestrator/worker/reviewer topology
    C: same as A, except Luna high replaces Sol low for easy/bounded work
    D: same as A, except Terra high replaces Sol low for easy/bounded work
    E: one single-agent deep-reasoning Sol configuration, no subagents
    F: planning phase produces implementation-plan.md, then a fresh
       single-agent implementation phase

`_harness_capability._model_family_tokens` decides whether a model id belongs
to the Sol, Luna, or Terra family, so the strategy check and the eligibility
check split ids the same way.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from _harness_capability import _model_family_tokens
from _routing_scenario import DifficultyClass

SCHEMA_VERSION = 1
MAX_CONCURRENCY_CEILING = 3
HANDOFF_ARTIFACT = "implementation-plan.md"
ARM_IDS: tuple[str, ...] = ("A", "B", "C", "D", "E", "F")


class RoutingConfigError(ValueError):
    """The benchmark config or a strategy in it is invalid. Never defaults."""


class Topology(str, Enum):
    FAN_OUT = "fan_out"
    SINGLE_AGENT = "single_agent"
    PLAN_THEN_FRESH = "plan_then_fresh"


@dataclass(frozen=True, slots=True)
class ModelEffort:
    model: str
    effort: str


@dataclass(frozen=True, slots=True)
class Reviewer:
    route: ModelEffort
    isolated: bool


@dataclass(frozen=True, slots=True)
class Strategy:
    arm: str
    topology: Topology
    orchestrator: ModelEffort
    workers: Mapping[DifficultyClass, ModelEffort]
    implementer: ModelEffort | None
    reviewer: Reviewer | None
    max_concurrency: int
    max_correction_rounds: int
    work_packages: int
    fresh_context_boundary: bool
    handoff_artifact: str | None


@dataclass(frozen=True, slots=True)
class HarnessRef:
    harness: str
    version: str


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    harnesses: tuple[HarnessRef, ...]
    strategies: tuple[Strategy, ...]
    overrides: Mapping[tuple[str, str], Strategy] = field(default_factory=dict)

    def strategy_for(self, arm: str, harness: str) -> Strategy:
        """The strategy as resolved for one harness (base plus its overrides)."""
        return self.overrides.get((arm, harness)) or next(
            s for s in self.strategies if s.arm == arm
        )


_TOP_KEYS = frozenset({"schema_version", "harnesses", "strategies"})
_STRATEGY_REQUIRED = frozenset({"arm", "topology", "orchestrator"})
_STRATEGY_OPTIONAL = frozenset(
    {
        "workers",
        "implementer",
        "reviewer",
        "max_concurrency",
        "max_correction_rounds",
        "work_packages",
        "fresh_context_boundary",
        "handoff_artifact",
        "harness_overrides",
    }
)
_OVERRIDABLE = (_STRATEGY_OPTIONAL | {"orchestrator"}) - {"harness_overrides"}


def _obj(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RoutingConfigError(f"{path}: expected an object, got {type(value).__name__}")
    return value


def _check_keys(
    data: dict[str, object], required: frozenset[str], optional: frozenset[str], path: str
) -> None:
    missing = required - data.keys()
    if missing:
        raise RoutingConfigError(f"{path}: missing required key(s) {sorted(missing)}")
    unknown = data.keys() - required - optional
    if unknown:
        raise RoutingConfigError(f"{path}: unknown key(s) {sorted(unknown)}")


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingConfigError(f"{path}: expected a non-empty string, got {value!r}")
    return value


def _count(value: object, path: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RoutingConfigError(f"{path}: expected an int >= {minimum}, got {value!r}")
    return value


def _route(value: object, path: str) -> ModelEffort:
    data = _obj(value, path)
    _check_keys(data, frozenset({"model", "effort"}), frozenset(), path)
    return ModelEffort(
        _text(data["model"], f"{path}.model"), _text(data["effort"], f"{path}.effort")
    )


def _reviewer(value: object, path: str) -> Reviewer | None:
    if value is None:
        return None
    data = _obj(value, path)
    _check_keys(data, frozenset({"model", "effort", "isolated"}), frozenset(), path)
    isolated = data["isolated"]
    if not isinstance(isolated, bool):
        raise RoutingConfigError(f"{path}.isolated: expected a bool, got {isolated!r}")
    return Reviewer(_route({"model": data["model"], "effort": data["effort"]}, path), isolated)


def _workers(value: object, path: str) -> dict[DifficultyClass, ModelEffort]:
    data = _obj(value, path)
    routes: dict[DifficultyClass, ModelEffort] = {}
    for key, raw in data.items():
        try:
            difficulty = DifficultyClass(key)
        except ValueError as exc:
            allowed = sorted(item.value for item in DifficultyClass)
            raise RoutingConfigError(f"{path}: {key!r} is not one of {allowed}") from exc
        routes[difficulty] = _route(raw, f"{path}.{key}")
    return routes


def _strategy_from(fields: dict[str, object], arm: str, path: str) -> Strategy:
    try:
        topology = Topology(fields["topology"])
    except ValueError as exc:
        allowed = sorted(item.value for item in Topology)
        raise RoutingConfigError(
            f"{path}.topology: {fields['topology']!r} not in {allowed}"
        ) from exc
    handoff = fields.get("handoff_artifact")
    implementer = fields.get("implementer")
    return Strategy(
        arm=arm,
        topology=topology,
        orchestrator=_route(fields["orchestrator"], f"{path}.orchestrator"),
        workers=_workers(fields.get("workers", {}), f"{path}.workers"),
        implementer=_route(implementer, f"{path}.implementer") if implementer else None,
        reviewer=_reviewer(fields.get("reviewer"), f"{path}.reviewer"),
        max_concurrency=_count(
            fields.get("max_concurrency", 1), f"{path}.max_concurrency", minimum=1
        ),
        max_correction_rounds=_count(
            fields.get("max_correction_rounds", 0), f"{path}.max_correction_rounds", minimum=0
        ),
        work_packages=_count(fields.get("work_packages", 1), f"{path}.work_packages", minimum=1),
        fresh_context_boundary=_flag(fields.get("fresh_context_boundary", False), path),
        handoff_artifact=_text(handoff, f"{path}.handoff_artifact")
        if handoff is not None
        else None,
    )


def _flag(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise RoutingConfigError(f"{path}.fresh_context_boundary: expected a bool, got {value!r}")
    return value


def _parse_strategy(
    raw: object, index: int, harnesses: set[str]
) -> tuple[Strategy, dict[str, Strategy]]:
    path = f"strategies[{index}]"
    data = _obj(raw, path)
    _check_keys(data, _STRATEGY_REQUIRED, _STRATEGY_OPTIONAL, path)
    arm = _text(data["arm"], f"{path}.arm")
    if arm not in ARM_IDS:
        raise RoutingConfigError(f"{path}.arm: {arm!r} is not one of {list(ARM_IDS)}")
    base_fields = {key: value for key, value in data.items() if key != "harness_overrides"}
    base = _strategy_from(base_fields, arm, path)
    resolved: dict[str, Strategy] = {}
    overrides = _obj(data.get("harness_overrides", {}), f"{path}.harness_overrides")
    for harness, patch in overrides.items():
        if harness not in harnesses:
            raise RoutingConfigError(
                f"{path}.harness_overrides: {harness!r} is not a configured harness"
            )
        patch_fields = _obj(patch, f"{path}.harness_overrides.{harness}")
        unknown = patch_fields.keys() - _OVERRIDABLE
        if unknown:
            raise RoutingConfigError(
                f"{path}.harness_overrides.{harness}: unknown key(s) {sorted(unknown)}"
            )
        merged = {**base_fields, **patch_fields}
        resolved[harness] = _strategy_from(merged, arm, f"{path}.harness_overrides.{harness}")
    return base, resolved


def _parse_harnesses(raw: object) -> tuple[HarnessRef, ...]:
    if not isinstance(raw, list) or not raw:
        raise RoutingConfigError("harnesses: expected a non-empty list")
    refs: list[HarnessRef] = []
    for index, item in enumerate(raw):
        data = _obj(item, f"harnesses[{index}]")
        _check_keys(data, frozenset({"harness", "version"}), frozenset(), f"harnesses[{index}]")
        refs.append(
            HarnessRef(
                _text(data["harness"], f"harnesses[{index}].harness"),
                _text(data["version"], f"harnesses[{index}].version"),
            )
        )
    names = [ref.harness for ref in refs]
    if len(set(names)) != len(names):
        raise RoutingConfigError(f"harnesses: duplicate harness in {names}")
    return tuple(refs)


def parse_config(data: object) -> BenchmarkConfig:
    """Parse a config document and enforce every arm invariant on every resolved strategy."""
    doc = _obj(data, "config")
    _check_keys(doc, _TOP_KEYS, frozenset(), "config")
    if doc["schema_version"] != SCHEMA_VERSION:
        raise RoutingConfigError(f"config.schema_version: expected {SCHEMA_VERSION}")
    harnesses = _parse_harnesses(doc["harnesses"])
    raw_strategies = doc["strategies"]
    if not isinstance(raw_strategies, list) or not raw_strategies:
        raise RoutingConfigError("strategies: expected a non-empty list")
    names = {ref.harness for ref in harnesses}
    strategies: list[Strategy] = []
    overrides: dict[tuple[str, str], Strategy] = {}
    for index, raw in enumerate(raw_strategies):
        base, resolved = _parse_strategy(raw, index, names)
        strategies.append(base)
        overrides.update({(base.arm, harness): item for harness, item in resolved.items()})
    arms = [item.arm for item in strategies]
    if len(set(arms)) != len(arms):
        raise RoutingConfigError(f"strategies: duplicate arm in {arms}")
    config = BenchmarkConfig(harnesses, tuple(strategies), overrides)
    check_config_invariants(config)
    return config


def load_config(path: Path) -> BenchmarkConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise RoutingConfigError(f"{path}: cannot read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RoutingConfigError(f"{path}: invalid JSON: {exc}") from exc
    return parse_config(raw)


def _in_family(route: ModelEffort | None, family: str) -> bool:
    return route is not None and family in _model_family_tokens(route.model)


def _worker(strategy: Strategy, difficulty: DifficultyClass) -> ModelEffort | None:
    return strategy.workers.get(difficulty)


def _fan_out_problems(strategy: Strategy) -> list[str]:
    problems: list[str] = []
    ordinary = _worker(strategy, DifficultyClass.ORDINARY_BOUNDED)
    fallback = _worker(strategy, DifficultyClass.FALLBACK_REASONING)
    if ordinary is None or fallback is None:
        problems.append("fan_out needs a worker route for both difficulty classes")
    if strategy.max_concurrency > MAX_CONCURRENCY_CEILING:
        problems.append(f"max_concurrency exceeds {MAX_CONCURRENCY_CEILING}")
    if (
        strategy.implementer is not None
        or strategy.handoff_artifact
        or strategy.fresh_context_boundary
    ):
        problems.append("fan_out has no implementer, handoff artifact, or fresh-context boundary")
    return problems


def _no_children_problems(strategy: Strategy) -> list[str]:
    problems: list[str] = []
    if strategy.workers or strategy.reviewer is not None:
        problems.append("no worker or reviewer subagents are allowed")
    if strategy.max_concurrency != 1 or strategy.work_packages != 1:
        problems.append("max_concurrency and work_packages must be 1")
    return problems


def _arm_specific_problems(strategy: Strategy) -> list[str]:
    ordinary = _worker(strategy, DifficultyClass.ORDINARY_BOUNDED)
    fallback = _worker(strategy, DifficultyClass.FALLBACK_REASONING)
    problems: list[str] = []
    match strategy.arm:
        case "A":
            ok = (
                _in_family(strategy.orchestrator, "sol")
                and strategy.orchestrator.effort == "medium"
            )
            ok = (
                ok
                and _in_family(ordinary, "sol")
                and ordinary is not None
                and ordinary.effort == "low"
            )
            ok = (
                ok
                and _in_family(fallback, "sol")
                and fallback is not None
                and fallback.effort == "medium"
            )
            if not ok or strategy.reviewer is not None:
                problems.append(
                    "A needs a Sol medium parent, Sol low and medium workers, no reviewer"
                )
        case "B":
            ok = _in_family(strategy.orchestrator, "sol") and _in_family(ordinary, "luna")
            if not ok or not _in_family(fallback, "terra"):
                problems.append(
                    "B needs a Sol orchestrator, Luna ordinary workers, Terra fallback workers"
                )
            if strategy.reviewer is None or not strategy.reviewer.isolated:
                problems.append("B needs an isolated reviewer")
        case "C" | "D":
            family = "luna" if strategy.arm == "C" else "terra"
            if not (
                _in_family(ordinary, family) and ordinary is not None and ordinary.effort == "high"
            ):
                problems.append(f"{strategy.arm} needs {family} high as the ordinary worker")
        case "E":
            if not _in_family(strategy.orchestrator, "sol"):
                problems.append("E needs a Sol configuration")
        case "F":
            if not _in_family(strategy.implementer, "sol") or not _in_family(
                strategy.orchestrator, "sol"
            ):
                problems.append("F needs Sol planner and Sol implementer")
            if not strategy.fresh_context_boundary or strategy.handoff_artifact != HANDOFF_ARTIFACT:
                problems.append(
                    f"F needs a fresh-context boundary and handoff artifact {HANDOFF_ARTIFACT}"
                )
    return problems


_TOPOLOGY_BY_ARM = {
    "A": Topology.FAN_OUT,
    "B": Topology.FAN_OUT,
    "C": Topology.FAN_OUT,
    "D": Topology.FAN_OUT,
    "E": Topology.SINGLE_AGENT,
    "F": Topology.PLAN_THEN_FRESH,
}


def strategy_problems(strategy: Strategy) -> list[str]:
    """Every invariant one resolved strategy breaks. Empty means valid."""
    if strategy.topology is not _TOPOLOGY_BY_ARM[strategy.arm]:
        return [f"arm {strategy.arm} requires topology {_TOPOLOGY_BY_ARM[strategy.arm].value}"]
    problems: list[str] = []
    if strategy.topology is Topology.FAN_OUT:
        problems += _fan_out_problems(strategy)
    elif strategy.topology is Topology.SINGLE_AGENT:
        problems += _no_children_problems(strategy)
        if strategy.implementer or strategy.handoff_artifact or strategy.fresh_context_boundary:
            problems.append("single_agent has no implementer, handoff, or fresh-context boundary")
    else:
        problems += _no_children_problems(strategy)
        if strategy.implementer is None:
            problems.append("plan_then_fresh needs an implementer")
    if not problems:
        problems += _arm_specific_problems(strategy)
    return problems


_HELD_FROM_ARM_A = (
    "orchestrator",
    "reviewer",
    "max_concurrency",
    "max_correction_rounds",
    "work_packages",
)


def _cd_problems(arm_a: Strategy, strategy: Strategy) -> list[str]:
    """C and D hold everything constant except the ordinary worker (#5422 fairness contract)."""
    problems = [
        f"{strategy.arm} differs from A in {name}"
        for name in _HELD_FROM_ARM_A
        if getattr(arm_a, name) != getattr(strategy, name)
    ]
    fallback = DifficultyClass.FALLBACK_REASONING
    if _worker(arm_a, fallback) != _worker(strategy, fallback):
        problems.append(f"{strategy.arm} differs from A in the fallback worker")
    return problems


def check_config_invariants(config: BenchmarkConfig) -> None:
    """Raise `RoutingConfigError` listing every broken A-F invariant."""
    problems: list[str] = []
    for harness in config.harnesses:
        for strategy in config.strategies:
            resolved = config.strategy_for(strategy.arm, harness.harness)
            for problem in strategy_problems(resolved):
                problems.append(f"arm {resolved.arm} on {harness.harness}: {problem}")
    by_arm = {item.arm: item for item in config.strategies}
    for arm in ("C", "D"):
        if arm in by_arm and "A" not in by_arm:
            problems.append(
                f"arm {arm} needs arm A in the same config for the held-constant comparison"
            )
        elif arm in by_arm:
            for harness in config.harnesses:
                held = _cd_problems(
                    config.strategy_for("A", harness.harness),
                    config.strategy_for(arm, harness.harness),
                )
                problems += [f"arm {arm} on {harness.harness}: {p}" for p in held]
    if problems:
        raise RoutingConfigError("; ".join(problems))
