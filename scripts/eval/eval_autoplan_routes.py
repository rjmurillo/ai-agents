#!/usr/bin/env python3
"""Score the autoplan long-tail route resolver against fixtures (issue #5389, part 1).

`/autoplan` routes a request in two steps. A model reads the high-traffic
table (prose), and on a miss it runs `resolve_route.py`, a deterministic
resolver. This eval drives the real resolver `main`, not a copy of its lookup,
and scores each request against an expected route. Model-free, offline, and
byte-stable across runs.

Executed families (the resolver decides these):
  explicit-skill, long-tail-single-domain, multi-domain-handoff,
  negative-noise, failure-fallback.

Reported as not executed, never as covered (a model or a static check owns
them, tracked in issue #5389 parts 2 and 3):
  high-traffic-direct, conditional-adjunct, lifecycle, composition-order.

A scenario expecting a specialist fails when the resolver falls through to the
orchestrator or to `none`. The report counts those separately as the
orchestrator-fallback rate.

Usage:
    uv run python scripts/eval/eval_autoplan_routes.py
    uv run python scripts/eval/eval_autoplan_routes.py --output report.json

Exit codes (ADR-035):
  0  every scenario matched its expectation.
  1  at least one scenario failed; the diff names expected and observed routes.
  2  config error: bad fixture file, or the resolver could not run.
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

EXECUTED_FAMILIES: tuple[str, ...] = (
    "explicit-skill",
    "long-tail-single-domain",
    "multi-domain-handoff",
    "negative-noise",
    "failure-fallback",
)

NOT_EXECUTED_FAMILIES: dict[str, str] = {
    "high-traffic-direct": "the routing table is prose a model reads",
    "conditional-adjunct": "the parent skill's own prose decides the adjunct",
    "lifecycle": "command sequence and gate composition are model behavior",
    "composition-order": "order is asserted from a model-driven run",
}

KINDS = frozenset({"explicit", "orchestrator", "specialist", "ambiguous", "none"})

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
    """Drop a `<namespace>:` prefix so fixtures hold across plugin identities."""
    if route is None:
        return None
    return route.split(":", 1)[-1]


def _scenario_from(raw: object, index: int) -> Scenario:
    if not isinstance(raw, dict):
        raise EvalConfigError(f"scenario {index} must be an object")
    expect = raw.get("expect")
    for key in ("id", "family", "request"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise EvalConfigError(f"scenario {index} needs a non-empty string {key!r}")
    if raw["family"] not in EXECUTED_FAMILIES:
        raise EvalConfigError(f"{raw['id']}: family {raw['family']!r} is not executed here")
    if not isinstance(expect, dict) or expect.get("kind") not in KINDS:
        raise EvalConfigError(f"{raw['id']}: expect.kind must be one of {sorted(KINDS)}")
    route = expect.get("route")
    if route is not None and not isinstance(route, str):
        raise EvalConfigError(f"{raw['id']}: expect.route must be a string or null")
    absent = expect.get("routes_absent", [])
    if not isinstance(absent, list) or not all(isinstance(a, str) for a in absent):
        raise EvalConfigError(f"{raw['id']}: expect.routes_absent must be a list of strings")
    return Scenario(raw["id"], raw["family"], raw["request"], expect["kind"], route, tuple(absent))


def load_scenarios(path: Path) -> list[Scenario]:
    """Read and validate a fixture file. Any defect raises, none is skipped."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvalConfigError(f"cannot read fixtures {path}: {exc}") from exc
    items = data.get("scenarios") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise EvalConfigError(f"{path}: 'scenarios' must be a non-empty list")
    scenarios = [_scenario_from(item, i) for i, item in enumerate(items)]
    ids = [s.id for s in scenarios]
    if len(set(ids)) != len(ids):
        raise EvalConfigError(f"{path}: duplicate scenario ids")
    return scenarios


def _load_resolver_main() -> Callable[[list[str]], int]:
    """Import the resolver's own `main` from its file path.

    The resolver ships inside a skill directory, so it is not an importable
    package. Calling `main` runs its real argument parsing and output path.
    """
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
    return cast(Callable[[list[str]], int], module.main)


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
    if not isinstance(result, dict) or result.get("kind") not in KINDS:
        raise EvalConfigError(f"resolver output has no valid kind: {out.getvalue()[:200]!r}")
    return result


def score(scenario: Scenario, observed: dict[str, Any]) -> list[str]:
    """Return failure lines for one scenario. Empty means the scenario passed."""
    route = bare(observed.get("route"))
    candidates = sorted(str(bare(c)) for c in observed.get("candidates", []))
    problems: list[str] = []
    if observed["kind"] != scenario.kind:
        problems.append(f"kind: expected {scenario.kind}, observed {observed['kind']}")
    if route != bare(scenario.route):
        problems.append(f"route: expected {bare(scenario.route)}, observed {route}")
    leaked = sorted(set(candidates) & set(scenario.routes_absent))
    if leaked:
        problems.append(f"unexpected skills selected: {', '.join(leaked)}")
    return problems


def _is_fallthrough(scenario: Scenario, observed: dict[str, Any]) -> bool:
    """A specialist was expected and the resolver returned the orchestrator or none."""
    return scenario.kind == "specialist" and observed["kind"] in ("orchestrator", "none")


def evaluate(scenarios: list[Scenario], skills_roots: list[str]) -> dict[str, Any]:
    """Run every scenario and build the deterministic report."""
    families: dict[str, dict[str, int]] = {f: {"total": 0, "passed": 0} for f in EXECUTED_FAMILIES}
    failures: list[dict[str, Any]] = []
    specialist_total = fallthrough = 0
    for scenario in scenarios:
        observed = run_resolver(scenario.request, skills_roots)
        problems = score(scenario, observed)
        families[scenario.family]["total"] += 1
        families[scenario.family]["passed"] += 0 if problems else 1
        specialist_total += scenario.kind == "specialist"
        fallthrough += _is_fallthrough(scenario, observed)
        if problems:
            failures.append({"id": scenario.id, "family": scenario.family, "problems": problems})
    passed = sum(f["passed"] for f in families.values())
    return {
        "total": len(scenarios),
        "passed": passed,
        "families": families,
        "orchestrator_fallback": {
            "specialist_fixtures": specialist_total,
            "fell_through": fallthrough,
        },
        "not_executed": dict(sorted(NOT_EXECUTED_FAMILIES.items())),
        "failures": failures,
    }


def render_text(report: dict[str, Any]) -> str:
    """Render the human-readable report and failure diff."""
    lines = [f"scenarios: {report['passed']}/{report['total']} passed"]
    for family, counts in sorted(report["families"].items()):
        lines.append(f"family {family}: {counts['passed']}/{counts['total']}")
    fb = report["orchestrator_fallback"]
    lines.append(f"orchestrator fallback: {fb['fell_through']}/{fb['specialist_fixtures']}")
    lines.extend(f"not executed {name}: {why}" for name, why in report["not_executed"].items())
    for failure in report["failures"]:
        lines.append(f"FAIL {failure['id']} [{failure['family']}]")
        lines.extend(f"  {problem}" for problem in failure["problems"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--skills-root", action="append", default=[], metavar="PATH[=NAMESPACE]")
    parser.add_argument("--output", type=Path, default=None, help="Also write the JSON report.")
    args = parser.parse_args(argv)
    try:
        report = evaluate(load_scenarios(args.fixtures), args.skills_root)
        if args.output is not None:
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", "utf-8")
    except (EvalConfigError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    print(render_text(report))
    return EXIT_FAIL if report["failures"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
