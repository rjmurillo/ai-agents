#!/usr/bin/env python3
# taste-lint: ignore file-size, resolver and model-driven scoring share one report and entry point.
"""Score autoplan routes: resolver fixtures and model-driven scenarios (issue #5389).

`/autoplan` routes a request in two steps. A model reads the high-traffic
table (prose), and on a miss it runs `resolve_route.py`, a deterministic
resolver. This eval drives the real resolver `main`, not a copy of its lookup,
and scores each request against an expected route. Model-free, offline, and
byte-stable across runs.

Executed families (the resolver decides these):
  explicit-skill, long-tail-single-domain, multi-domain-handoff,
  negative-noise, failure-fallback.

Model-driven families (issue #6290, part 2) are scenarios in
`tests/evals/skill-scenarios/autoplan.json`, run by `eval-rule-activation.py`
against a live model. This script never calls a model. It validates that file
and, given `--model-results` (the `--output` of that run), reports per family
the scenarios, reachable routes, exercised, scored, and passed counts apart.
Without results the families read "not scored", never as covered. A model
miss is advisory and never changes the exit code, so CI does not gate on an
LLM judge.

A scenario expecting a specialist fails when the resolver falls through to the
orchestrator or to `none`. The report counts the two outcomes separately.

Usage:
    uv run python scripts/eval/eval_autoplan_routes.py
    uv run python scripts/eval/eval_autoplan_routes.py --output report.json
    uv run python scripts/eval/eval_autoplan_routes.py --model-results run.json

Exit codes (ADR-035):
  0  every scenario matched its expectation.
  1  at least one resolver scenario failed; the diff names expected and observed routes.
  2  config error: bad fixture or scenario file, bad results file, or the resolver
     could not run.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[2]
RESOLVER = REPO_ROOT / ".claude" / "skills" / "autoplan" / "scripts" / "resolve_route.py"
DEFAULT_FIXTURES = REPO_ROOT / "tests" / "evals" / "autoplan-routes" / "routes.json"
DEFAULT_MODEL_SCENARIOS = REPO_ROOT / "tests" / "evals" / "skill-scenarios" / "autoplan.json"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

EXECUTED_FAMILIES: tuple[str, ...] = (
    "explicit-skill",
    "long-tail-single-domain",
    "multi-domain-handoff",
    "negative-noise",
    "failure-fallback",
)

MODEL_FAMILIES: tuple[str, ...] = (
    "high-traffic-direct",
    "conditional-adjunct",
    "lifecycle",
    "composition-order",
    "dx-activation",
    "advisor-vs-buy-vs-build",
)
# The runner's `full` mechanism puts the autoplan body in the system prompt,
# which is the condition autoplan runs under.
MODEL_MECHANISM = "full"
# Judge rubric is 1 to 5 (eval-rule-activation.py MIN/MAX_RUBRIC_SCORE).
MODEL_PASS_SCORE = 4.0
MODEL_MIN_SCORE = 1.0
MODEL_MAX_SCORE = 5.0
# An order step that names a workflow step rather than an installed route.
NON_ROUTE_STEPS = frozenset({"incorporation"})

KINDS = frozenset({"explicit", "orchestrator", "specialist", "ambiguous", "none"})
# Kinds whose fixture must name the route it asserts; the others carry null.
ROUTE_KINDS = frozenset({"explicit", "orchestrator", "specialist"})

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2


class EvalConfigError(Exception):
    """A fixture or resolver problem that must fail the run as exit 2."""


@dataclass(frozen=True)
class Scenario:
    """One request and the route the resolver must return for it."""

    id: str
    family: str
    request: str
    kind: str
    route: str | None
    routes_absent: tuple[str, ...]


def bare(route: str | None) -> str | None:
    """Drop a `<namespace>:` prefix."""
    if route is None:
        return None
    return route.split(":", 1)[-1]


def route_matches(expected: str | None, observed: str | None) -> bool:
    """Compare a fixture route with the resolver's route.

    A bare fixture name matches that skill in any namespace, so fixtures hold
    across plugin identities. A qualified name (`ns:skill`) must match exactly,
    which is how a fixture pins the namespace in a mixed catalog.
    """
    if expected is None or observed is None:
        return expected is observed
    if ":" in expected:
        return expected == observed
    return expected == bare(observed)


def _expectation(scenario_id: str, expect: object) -> tuple[str, str | None, tuple[str, ...]]:
    """Validate one `expect` block and return (kind, route, routes_absent)."""
    if not isinstance(expect, dict):
        raise EvalConfigError(f"{scenario_id}: expect must be an object")
    kind = expect.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        raise EvalConfigError(f"{scenario_id}: expect.kind must be one of {sorted(KINDS)}")
    if "route" not in expect:
        raise EvalConfigError(f"{scenario_id}: expect.route is required (use null for none)")
    route = expect["route"]
    if kind in ROUTE_KINDS and not (isinstance(route, str) and route.strip()):
        raise EvalConfigError(
            f"{scenario_id}: expect.route must be a non-empty string for kind {kind}"
        )
    if kind not in ROUTE_KINDS and route is not None:
        raise EvalConfigError(f"{scenario_id}: expect.route must be null for kind {kind}")
    absent = expect.get("routes_absent", [])
    if not isinstance(absent, list) or not all(isinstance(a, str) for a in absent):
        raise EvalConfigError(f"{scenario_id}: expect.routes_absent must be a list of strings")
    return kind, route, tuple(absent)


def _scenario_from(raw: object, index: int) -> Scenario:
    if not isinstance(raw, dict):
        raise EvalConfigError(f"scenario {index} must be an object")
    for key in ("id", "family", "request"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise EvalConfigError(f"scenario {index} needs a non-empty string {key!r}")
    if raw["family"] not in EXECUTED_FAMILIES:
        raise EvalConfigError(f"{raw['id']}: family {raw['family']!r} is not executed here")
    kind, route, absent = _expectation(raw["id"], raw.get("expect"))
    return Scenario(raw["id"], raw["family"], raw["request"], kind, route, absent)


def load_scenarios(path: Path) -> list[Scenario]:
    """Read and validate a fixture file. Any defect raises, none is skipped."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvalConfigError(f"cannot read fixtures {path}: {exc}") from exc
    if isinstance(data, dict) and data.get("schema_version") != SCHEMA_VERSION:
        raise EvalConfigError(
            f"{path}: schema_version must be {SCHEMA_VERSION}, got {data.get('schema_version')!r}"
        )
    items = data.get("scenarios") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise EvalConfigError(f"{path}: 'scenarios' must be a non-empty list")
    scenarios = [_scenario_from(item, i) for i, item in enumerate(items)]
    ids = [s.id for s in scenarios]
    if len(set(ids)) != len(ids):
        raise EvalConfigError(f"{path}: duplicate scenario ids")
    return scenarios


_RESOLVER_CACHE: dict[Path, Callable[[list[str]], int]] = {}


def _load_resolver_main() -> Callable[[list[str]], int]:
    """Import the resolver's own `main` from its file path.

    The resolver ships inside a skill directory, so it is not an importable
    package. Calling `main` runs its real argument parsing and output path.
    """
    if RESOLVER in _RESOLVER_CACHE:
        return _RESOLVER_CACHE[RESOLVER]
    spec = importlib.util.spec_from_file_location("autoplan_resolve_route", RESOLVER)
    if spec is None or spec.loader is None:
        raise EvalConfigError(f"cannot load resolver: {RESOLVER}")
    module = importlib.util.module_from_spec(spec)
    # The resolver defines dataclasses, which look their module up in sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError, ImportError) as exc:
        raise EvalConfigError(f"cannot load resolver {RESOLVER}: {exc}") from exc
    main = getattr(module, "main", None)
    if not callable(main):
        raise EvalConfigError(f"resolver {RESOLVER} defines no callable main")
    main = cast(Callable[[list[str]], int], main)
    _RESOLVER_CACHE[RESOLVER] = main
    return main


def _validate_resolver_payload(result: object, raw: str) -> None:
    """Fail closed unless the resolver payload carries every contract field."""
    if not isinstance(result, dict) or not isinstance(result.get("kind"), str):
        raise EvalConfigError(f"resolver output has no valid kind: {raw[:200]!r}")
    if result["kind"] not in KINDS:
        raise EvalConfigError(f"resolver output has no valid kind: {raw[:200]!r}")
    missing = [key for key in ("route", "candidates") if key not in result]
    if missing:
        raise EvalConfigError(f"resolver output lacks {', '.join(missing)}: {raw[:200]!r}")
    candidates = result["candidates"]
    if not isinstance(candidates, list) or not all(isinstance(c, str) for c in candidates):
        raise EvalConfigError(f"resolver candidates must be a list of strings: {candidates!r:.200}")
    if result["route"] is not None and not isinstance(result["route"], str):
        raise EvalConfigError(f"resolver route must be a string or null: {result['route']!r:.200}")


def run_resolver(request: str, skills_roots: list[str]) -> dict[str, Any]:
    """Run the real resolver `main` for one request and parse its JSON line."""
    argv = ["--request", request]
    for root in skills_roots:
        argv += ["--skills-root", root]
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = _load_resolver_main()(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
    if code != 0:
        raise EvalConfigError(f"resolver exited {code}: {err.getvalue().strip()[:200]}")
    try:
        result = json.loads(out.getvalue())
    except ValueError as exc:
        raise EvalConfigError(f"resolver output is not JSON: {out.getvalue()[:200]!r}") from exc
    _validate_resolver_payload(result, out.getvalue())
    return result


def _leaked(absent: tuple[str, ...], candidates: list[str]) -> list[str]:
    """Candidates a scenario forbids. A bare entry matches any namespace."""
    return sorted(c for c in candidates if any(route_matches(a, c) for a in absent))


def score(scenario: Scenario, observed: dict[str, Any]) -> list[str]:
    """Return failure lines for one scenario. Empty means the scenario passed.

    Every failure starts with the full expected-versus-observed line, so a
    candidate-only failure still shows both routes.
    """
    route = observed.get("route")
    candidates = sorted(str(c) for c in observed.get("candidates", []))
    problems: list[str] = []
    if observed["kind"] != scenario.kind:
        problems.append(f"kind: expected {scenario.kind}, observed {observed['kind']}")
    if not route_matches(scenario.route, route):
        problems.append(f"route: expected {scenario.route}, observed {route}")
    leaked = _leaked(scenario.routes_absent, candidates)
    if leaked:
        problems.append(f"unexpected skills selected: {', '.join(leaked)}")
    if problems:
        problems.insert(
            0,
            f"expected kind={scenario.kind} route={scenario.route}; "
            f"observed kind={observed['kind']} route={route} candidates={candidates}",
        )
    return problems


@dataclass(frozen=True)
class ModelScenario:
    """One model-driven scenario: the routes it expects, forbids, and orders."""

    id: str
    family: str
    expected_route: tuple[str, ...]
    forbidden_routes: tuple[str, ...]
    expected_order: tuple[str, ...]


def _string_list(
    scenario_id: str, raw: dict[str, Any], key: str, required: bool
) -> tuple[str, ...]:
    value = raw.get(key, None if required else [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise EvalConfigError(f"{scenario_id}: {key} must be a list of non-empty strings")
    if required and not value:
        raise EvalConfigError(f"{scenario_id}: {key} must not be empty")
    return tuple(value)


def _model_scenario_from(raw: object, index: int) -> ModelScenario:
    if not isinstance(raw, dict):
        raise EvalConfigError(f"model scenario {index} must be an object")
    for key in ("id", "family", "input", "expected_gate", "rationale"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise EvalConfigError(f"model scenario {index} needs a non-empty string {key!r}")
    sid = raw["id"]
    if raw["family"] not in MODEL_FAMILIES:
        raise EvalConfigError(f"{sid}: family {raw['family']!r} is not a model-driven family")
    expected = _string_list(sid, raw, "expected_route", required=True)
    forbidden = _string_list(sid, raw, "forbidden_routes", required=True)
    order = _string_list(sid, raw, "expected_order", required=raw["family"] == "composition-order")
    stray = [step for step in order if step not in expected and step not in NON_ROUTE_STEPS]
    if stray:
        raise EvalConfigError(f"{sid}: expected_order names steps outside expected_route: {stray}")
    return ModelScenario(sid, raw["family"], expected, forbidden, order)


def load_model_scenarios(path: Path) -> list[ModelScenario]:
    """Read and validate the model-driven scenario file. Any defect raises.

    The file is also the input of `eval-rule-activation.py`, which owns the
    `skill_path`, `input`, `expected_signals`, and `expected_gate` fields. This
    loader checks the extra fields that name the route, the negative
    constraint, and the order, so a file the runner accepts but that scores
    nothing about routes is refused here.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvalConfigError(f"cannot read model scenarios {path}: {exc}") from exc
    items = data.get("scenarios") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise EvalConfigError(f"{path}: 'scenarios' must be a non-empty list")
    scenarios = [_model_scenario_from(item, i) for i, item in enumerate(items)]
    ids = [s.id for s in scenarios]
    if len(set(ids)) != len(ids):
        raise EvalConfigError(f"{path}: duplicate model scenario ids")
    missing = sorted(set(MODEL_FAMILIES) - {s.family for s in scenarios})
    if missing:
        raise EvalConfigError(f"{path}: no scenario for model-driven families {missing}")
    return scenarios


def route_exists(name: str) -> bool:
    """True when `name` is an installed skill or agent in this checkout."""
    return (SKILLS_DIR / name / "SKILL.md").is_file() or (AGENTS_DIR / f"{name}.md").is_file()


def _is_rubric_score(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return MODEL_MIN_SCORE <= value <= MODEL_MAX_SCORE


def _cell_score(result: dict[str, Any]) -> float | None:
    """The scored cell of one result, or None when the run did not grade it.

    Agrees with `_scenario_score_triple` in `eval-rule-activation.py` on the
    `cell_score` path (pinned by `test_cell_score_agrees_with_the_runner`).
    Stricter than the runner: a judge-failed cell, and a legacy cell with only
    the score triple, are unmeasured here. An errored, ungraded, or off-rubric
    cell is unmeasured too, never a zero.
    """
    mechanisms = result.get("mechanisms")
    cell = mechanisms.get(MODEL_MECHANISM) if isinstance(mechanisms, dict) else None
    if not isinstance(cell, dict) or "error" in cell:
        return None
    scores = cell.get("scores")
    if not isinstance(scores, dict) or scores.get("graded") is False or scores.get("judge_failed"):
        return None
    value = scores.get("cell_score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if _is_rubric_score(value) else None


def load_model_results(path: Path, skill_id: str = "autoplan") -> dict[str, dict[str, Any]]:
    """Read an `eval-rule-activation.py --output` file into {scenario id: result}."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvalConfigError(f"cannot read model results {path}: {exc}") from exc
    rules = data.get("rules") if isinstance(data, dict) else None
    target = rules.get(skill_id) if isinstance(rules, dict) else None
    items = target.get("scenarios") if isinstance(target, dict) else None
    if not isinstance(items, list):
        raise EvalConfigError(f"{path}: no rules.{skill_id}.scenarios list in the results")
    return {
        item["id"]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def evaluate_model(
    scenarios: list[ModelScenario], results: dict[str, dict[str, Any]] | None
) -> dict[str, Any]:
    """Count each model-driven family's layers apart. Never touches a model.

    `scenarios` is what the file defines. `reachable` counts scenarios whose
    every named route is installed. `exercised` counts scenarios the run has a
    result for, `scored` those with a graded cell, and `passed` those at or
    above MODEL_PASS_SCORE. With no results, exercised, scored, and passed
    stay 0 and `accuracy` is None: not scored, never zero.
    """
    families: dict[str, dict[str, Any]] = {
        f: {"scenarios": 0, "reachable": 0, "exercised": 0, "scored": 0, "passed": 0}
        for f in MODEL_FAMILIES
    }
    unreachable: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []
    for scenario in scenarios:
        counts = families[scenario.family]
        counts["scenarios"] += 1
        named = (*scenario.expected_route, *scenario.forbidden_routes)
        gone = [name for name in named if not route_exists(name)]
        counts["reachable"] += 0 if gone else 1
        if gone:
            unreachable.append({"id": scenario.id, "routes": gone})
        result = None if results is None else results.get(scenario.id)
        if result is None:
            continue
        counts["exercised"] += 1
        cell = _cell_score(result)
        if cell is None:
            continue
        counts["scored"] += 1
        counts["passed"] += cell >= MODEL_PASS_SCORE
        if cell < MODEL_PASS_SCORE:
            misses.append({"id": scenario.id, "family": scenario.family, "score": cell})
    for counts in families.values():
        counts["accuracy"] = counts["passed"] / counts["scored"] if counts["scored"] else None
    return {
        "run_supplied": results is not None,
        "families": families,
        "unreachable": unreachable,
        "misses": misses,
    }


def evaluate(
    scenarios: list[Scenario],
    skills_roots: list[str],
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run every scenario and build the deterministic report.

    `model` is the `evaluate_model` section; it rides along unchanged and
    never affects `failures`, so a model miss cannot fail the run.
    """
    families: dict[str, dict[str, int]] = {f: {"total": 0, "passed": 0} for f in EXECUTED_FAMILIES}
    failures: list[dict[str, Any]] = []
    specialist_total = to_orchestrator = unresolved = 0
    for scenario in scenarios:
        observed = run_resolver(scenario.request, skills_roots)
        problems = score(scenario, observed)
        families[scenario.family]["total"] += 1
        families[scenario.family]["passed"] += 0 if problems else 1
        specialist_total += scenario.kind == "specialist"
        if scenario.kind == "specialist":
            to_orchestrator += observed["kind"] == "orchestrator"
            unresolved += observed["kind"] == "none"
        if problems:
            failures.append({"id": scenario.id, "family": scenario.family, "problems": problems})
    passed = sum(f["passed"] for f in families.values())
    return {
        "total": len(scenarios),
        "passed": passed,
        "families": families,
        "orchestrator_fallback": {
            "specialist_fixtures": specialist_total,
            "to_orchestrator": to_orchestrator,
            "unresolved": unresolved,
        },
        "model_driven": model,
        "failures": failures,
    }


def render_model(model: dict[str, Any] | None) -> list[str]:
    """Render the model-driven section: layer counts apart, accuracy or not scored."""
    if model is None:
        return []
    lines = []
    for family, c in model["families"].items():
        acc = "not scored" if c["accuracy"] is None else f"{c['accuracy']:.0%}"
        lines.append(
            f"model family {family}: scenarios={c['scenarios']} reachable={c['reachable']} "
            f"exercised={c['exercised']} scored={c['scored']} passed={c['passed']} accuracy={acc}"
        )
    if not model["run_supplied"]:
        lines.append("model-driven families not scored: pass --model-results from a live run")
    lines.extend(f"unreachable {u['id']}: {', '.join(u['routes'])}" for u in model["unreachable"])
    lines.extend(
        f"MODEL-MISS {m['id']} [{m['family']}] score={m['score']:.2f} (advisory)"
        for m in model["misses"]
    )
    return lines


def render_text(report: dict[str, Any]) -> str:
    """Render the human-readable report and failure diff."""
    lines = [f"scenarios: {report['passed']}/{report['total']} passed"]
    for family, counts in sorted(report["families"].items()):
        lines.append(f"family {family}: {counts['passed']}/{counts['total']}")
    fb = report["orchestrator_fallback"]
    total = fb["specialist_fixtures"]
    lines.append(f"orchestrator fallback: {fb['to_orchestrator']}/{total}")
    lines.append(f"unresolved (none): {fb['unresolved']}/{total}")
    lines.extend(render_model(report["model_driven"]))
    for failure in report["failures"]:
        lines.append(f"FAIL {failure['id']} [{failure['family']}]")
        lines.extend(f"  {problem}" for problem in failure["problems"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--skills-root", action="append", default=[], metavar="PATH[=NAMESPACE]")
    parser.add_argument("--model-scenarios", type=Path, default=DEFAULT_MODEL_SCENARIOS)
    parser.add_argument(
        "--model-results",
        type=Path,
        default=None,
        help="Output of eval-rule-activation.py run on the model scenarios (needs a live model).",
    )
    parser.add_argument("--output", type=Path, default=None, help="Also write the JSON report.")
    args = parser.parse_args(argv)
    try:
        results = None if args.model_results is None else load_model_results(args.model_results)
        model = evaluate_model(load_model_scenarios(args.model_scenarios), results)
        report = evaluate(load_scenarios(args.fixtures), args.skills_root, model)
        if args.output is not None:
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    except (EvalConfigError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(render_text(report))
    return EXIT_FAIL if report["failures"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
