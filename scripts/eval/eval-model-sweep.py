#!/usr/bin/env python3
"""Eval model-sweep runner (Issue #2840, acceptance criterion 2).

Sweep one agent's fixtures across several candidate models, score each with
the existing single-model evaluator, and report a scored winner with effect
size so a ``model:`` pin can be kept ONLY with evidence (else dropped to the
harness default).

This is a thin orchestrator. It does NOT re-implement the run loop, scoring,
persistence, or statistics: each candidate model is evaluated by shelling out
to the fully-tested ``eval-agent-vs-baseline.py`` (agent variant), then the
resulting ``report.json`` is compared across models by ``_model_sweep_core``.
The runner is injected (``ModelEvalRunner``, a structural Protocol) so the
orchestration and the KEEP_PIN/DROP_PIN decision are unit-testable without
any API spend; the live implementation is ``SubprocessModelEvalRunner``.

Prerequisite: every swept model must have a pricing rate in
``MODEL_PRICING_RATES_USD_PER_1K_TOKENS`` (``_eval_common.py``); the base
evaluator hard-fails on an unpriced model (Issue #2858). The sweep pre-checks
this and prints an actionable error naming the unpriced models. It does NOT
invent pricing.

Exit codes (AGENTS.md): 0 ok, 1 logic, 2 config, 3 external, 4 auth. A child
run's exit-code class (1/2/4) is preserved; any other child failure surfaces
as 3 (external) to the sweep.

Usage:
    eval-model-sweep.py --agent security --fixtures tests/evals/skills/security \\
        --models claude-sonnet-4-6,claude-opus-4-6 --n-runs 3
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import re
import subprocess  # S404: invokes a sibling eval script with a fixed, validated argv
import sys
import uuid
from pathlib import Path
from typing import Any, Protocol

from _eval_common import MODEL_PRICING_RATES_USD_PER_1K_TOKENS
from _model_sweep_core import (
    DEFAULT_MIN_EFFECT,
    DEFAULT_SEED,
    ModelResult,
    SweepDecisionError,
    build_report,
    decide,
)

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
BASE_EVAL_SCRIPT = EVAL_DIR / "eval-agent-vs-baseline.py"

# Mirrors eval-agent-vs-baseline.DEFAULT_MODEL. The base script's filename has
# hyphens (not importable as a module), so the value is duplicated here and a
# drift guard test asserts the two stay equal.
DEFAULT_MODEL = "claude-sonnet-4-6"
REPORTS_DIR_TEMPLATE = "evals/{agent}-spike/reports"

# The child evaluator makes live LLM API calls; a stalled provider must not hang
# the sweep forever. Bound each child run with a wall-clock timeout (seconds).
DEFAULT_CHILD_TIMEOUT_S = 1800

_AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class ChildRunError(Exception):
    """Raised when the base evaluator exits non-zero for a model."""

    def __init__(self, model_id: str, returncode: int, stderr: str) -> None:
        super().__init__(
            f"eval-agent-vs-baseline failed for model {model_id!r} "
            f"(exit {returncode}): {stderr.strip()[:400]}"
        )
        self.model_id = model_id
        self.returncode = returncode


def _agent_name_arg(value: str) -> str:
    if not _AGENT_NAME_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"--agent must match {_AGENT_NAME_RE.pattern} (got {value!r})"
        )
    return value


def parse_models_arg(raw: str, *, default_model: str) -> list[str]:
    """Parse ``--models`` into a validated, de-duplicated, order-preserving list.

    The default model is always included (appended if absent) because the
    comparison needs it as the anchor. Each id is path-safe (it becomes part of
    a run-id joined under REPO_ROOT) and non-empty.
    """
    ids: list[str] = []
    for token in raw.split(","):
        model = token.strip()
        if not model:
            continue
        if not _MODEL_ID_RE.match(model):
            raise argparse.ArgumentTypeError(
                f"model id must match {_MODEL_ID_RE.pattern} (got {model!r})"
            )
        if model not in ids:
            ids.append(model)
    if not ids:
        raise argparse.ArgumentTypeError("--models must list at least one model id")
    if not _MODEL_ID_RE.match(default_model):
        raise argparse.ArgumentTypeError(
            f"--default-model must match {_MODEL_ID_RE.pattern} (got {default_model!r})"
        )
    if default_model not in ids:
        ids.append(default_model)
    return ids


def validate_models_priced(models: list[str]) -> list[str]:
    """Return the subset of *models* lacking a pricing rate (empty == all ok)."""
    return [m for m in models if m not in MODEL_PRICING_RATES_USD_PER_1K_TOKENS]


def _sanitize_for_run_id(model_id: str) -> str:
    """Map a model id to the run-id charset ([A-Za-z0-9_-]) deterministically."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", model_id)


def make_run_id(model_id: str, *, unique: str | None = None) -> str:
    """Build a path-safe, per-model run id: ``sweep-<model>-<8hex>``.

    The unique suffix is preserved even for long model ids: the sanitized
    model slug is truncated to fit the 64-char run-id budget so two long ids
    can never collapse to the same run id (which would collide report dirs).
    """
    suffix = unique or uuid.uuid4().hex[:8]
    prefix = "sweep-"
    # 64 total, minus prefix, minus the "-" joiner, minus the suffix.
    slug_budget = 64 - len(prefix) - 1 - len(suffix)
    slug = _sanitize_for_run_id(model_id)[:slug_budget]
    run_id = f"{prefix}{slug}-{suffix}"
    if not _RUN_ID_RE.match(run_id):
        raise ValueError(f"generated run id is not path-safe: {run_id!r}")
    return run_id


def build_child_argv(
    *,
    agent: str,
    fixtures: Path,
    model_id: str,
    n_runs: int,
    run_id: str,
    provider: str | None,
) -> list[str]:
    """Argv for one base-evaluator invocation (agent variant, one model)."""
    argv = [
        sys.executable,
        str(BASE_EVAL_SCRIPT),
        "--agent",
        agent,
        "--fixtures",
        str(fixtures),
        "--model",
        model_id,
        "--n-runs",
        str(n_runs),
        "--run-id",
        run_id,
    ]
    if provider:
        argv += ["--provider", provider]
    return argv


def child_report_path(agent: str, run_id: str) -> Path:
    """Path to the report.json the base evaluator writes for a run."""
    return REPO_ROOT / REPORTS_DIR_TEMPLATE.format(agent=agent) / run_id / "report.json"


def _child_cost_usd(report: dict[str, Any]) -> float | None:
    """Read a child report's USD cost, carrying its null through unchanged.

    A request-metered child writes ``cost_estimate_usd: null`` because its
    provider publishes no per-token price. `dict.get` cannot default that away:
    the key is present and holds None, so the default never fires and
    ``float(None)`` raises. The child already decided what its own run cost;
    re-deriving it here would be a second answer to a settled question.
    """
    cost = report.get("cost_estimate_usd", 0.0)
    return None if cost is None else float(cost)


def parse_report(report: dict[str, Any], *, model_id: str) -> ModelResult:
    """Extract a ``ModelResult`` (agent variant) from a report.json dict.

    Fixtures the base evaluator excluded for flakiness are dropped here too:
    the report's headline ``agent_recall`` is computed on the STABLE subset
    (flaky fixtures excluded), so the per-fixture rates feeding the paired CI
    must exclude the same fixtures or the CI and the point delta would span
    different fixture sets.

    A child that exits 0 but writes a schema-invalid report (e.g. ``{}`` or a
    non-object) is an EXTERNAL failure, not a valid empty result. The consumed
    identity fields (``fixture_set_sha``, ``agent_recall``,
    ``per_fixture_pass_rates``) are therefore required; a missing/mistyped one
    raises so the runner maps it to ``EXIT_EXTERNAL`` instead of silently
    producing a degenerate ``ModelResult``.
    """
    if not isinstance(report, dict):
        raise ValueError(f"report for {model_id} is not a JSON object")
    for field in ("fixture_set_sha", "agent_recall", "per_fixture_pass_rates"):
        if field not in report:
            raise KeyError(f"report for {model_id} missing required field: {field}")
    fixture_set_sha = report["fixture_set_sha"]
    if not isinstance(fixture_set_sha, str) or not fixture_set_sha:
        raise ValueError(f"report for {model_id} has empty/invalid fixture_set_sha")
    agent_recall = report["agent_recall"]
    if (
        not isinstance(agent_recall, (int, float))
        or isinstance(agent_recall, bool)
        or not math.isfinite(agent_recall)
        or not 0.0 <= float(agent_recall) <= 1.0
    ):
        raise ValueError(f"report for {model_id} agent_recall must be finite and in [0, 1]")
    per_fixture = report["per_fixture_pass_rates"]
    if not isinstance(per_fixture, dict) or not per_fixture:
        raise ValueError(f"report for {model_id} per_fixture_pass_rates must be a non-empty object")
    excluded_raw = report.get("flaky_fixtures_excluded")
    # Must be a list of fixture ids. A bare string would make set() iterate
    # characters (silently excluding fixtures whose id is a single char),
    # so reject anything that is not a list before building the set.
    if excluded_raw is None:
        excluded: set[str] = set()
    elif isinstance(excluded_raw, list):
        # Elements come from an external report artifact and are used as set
        # membership keys against string fixture ids; a non-string (or an
        # unhashable dict/list) would either never match or crash set().
        if not all(isinstance(x, str) for x in excluded_raw):
            raise ValueError(
                f"report for {model_id} flaky_fixtures_excluded must be a list of strings"
            )
        excluded = set(excluded_raw)
    else:
        raise ValueError(f"report for {model_id} flaky_fixtures_excluded is not a list")
    if "error_count" not in report:
        raise KeyError(f"report for {model_id} missing required field: error_count")
    error_count = report["error_count"]
    if not isinstance(error_count, int) or isinstance(error_count, bool):
        raise ValueError(f"report for {model_id} error_count must be a non-negative integer")
    if error_count < 0:
        raise ValueError(f"report for {model_id} error_count must be a non-negative integer")
    rates: dict[str, list[float]] = {}
    for fixture_id, variants in per_fixture.items():
        if fixture_id in excluded:
            continue
        if not isinstance(variants, dict):
            raise ValueError(
                f"report for {model_id} fixture {fixture_id!r} variants must be an object"
            )
        agent_rates = variants.get("agent")
        if not isinstance(agent_rates, list) or not agent_rates:
            raise ValueError(
                f"report for {model_id} fixture {fixture_id!r} agent rates must be a non-empty list"
            )
        parsed_rates: list[float] = []
        for index, rate in enumerate(agent_rates):
            if (
                not isinstance(rate, (int, float))
                or isinstance(rate, bool)
                or not math.isfinite(rate)
                or not 0.0 <= float(rate) <= 1.0
            ):
                raise ValueError(
                    f"report for {model_id} fixture {fixture_id!r} agent "
                    f"rate {index} must be finite and in [0, 1]"
                )
            parsed_rates.append(float(rate))
        rates[str(fixture_id)] = parsed_rates
    if not rates:
        raise ValueError(f"report for {model_id} has no stable agent rates")
    return ModelResult(
        model_id=model_id,
        agent_recall=float(agent_recall),
        per_fixture_agent_rates=rates,
        tokens_in=int(report.get("total_tokens_in", 0)),
        tokens_out=int(report.get("total_tokens_out", 0)),
        cost_usd=_child_cost_usd(report),
        cost_basis=str(report.get("cost_basis", "usd")),
        error_count=error_count,
        fixture_set_sha=str(fixture_set_sha),
    )


class ModelEvalRunner(Protocol):
    """Structural type for the per-model evaluation step (dependency injection).

    ``run_sweep`` depends on this Protocol, not the concrete
    ``SubprocessModelEvalRunner``, so tests inject a fake runner with no API
    spend while the live path stays the only subprocess caller. A conforming
    runner evaluates one model id and returns its ``ModelResult`` or raises
    ``ChildRunError`` (carrying the child exit-code class).
    """

    def run(self, model_id: str) -> ModelResult: ...


class SubprocessModelEvalRunner:
    """Default runner: evaluate one model by shelling out to the base script.

    Reuses the fully-tested live path (retry, idempotency, persistence,
    scoring, aggregation) and parses the resulting ``report.json`` into a
    ``ModelResult`` (which carries the report's ``fixture_set_sha``).
    """

    def __init__(
        self,
        *,
        agent: str,
        fixtures: Path,
        n_runs: int,
        provider: str | None,
        child_timeout: float = DEFAULT_CHILD_TIMEOUT_S,
        env: dict[str, str] | None = None,
    ) -> None:
        self._agent = agent
        self._fixtures = fixtures
        self._n_runs = n_runs
        self._provider = provider
        self._child_timeout = child_timeout
        self._env = env

    def run(self, model_id: str) -> ModelResult:
        run_id = make_run_id(model_id)
        argv = build_child_argv(
            agent=self._agent,
            fixtures=self._fixtures,
            model_id=model_id,
            n_runs=self._n_runs,
            run_id=run_id,
            provider=self._provider,
        )
        try:
            completed = subprocess.run(  # S603: argv is fixed + validated, shell=False
                argv,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                env=self._env if self._env is not None else os.environ.copy(),
                check=False,
                timeout=self._child_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            # A hung child (e.g. stalled provider) is an EXTERNAL failure, not a
            # crash of the sweep itself. Surface it so run_sweep maps it to
            # EXIT_EXTERNAL instead of blocking indefinitely.
            raise ChildRunError(
                model_id,
                EXIT_EXTERNAL,
                f"child timed out after {self._child_timeout:g}s",
            ) from exc
        if completed.returncode != EXIT_OK:
            raise ChildRunError(model_id, completed.returncode, completed.stderr)
        report_path = child_report_path(self._agent, run_id)
        # The child exited 0 but its report artifact is an external dependency:
        # a missing or malformed file is an EXTERNAL failure, not an unhandled
        # crash. Surface it as ChildRunError so run_sweep maps it per contract.
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            return parse_report(report, model_id=model_id)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ChildRunError(
                model_id,
                EXIT_EXTERNAL,
                f"child exited 0 but report at {report_path} is unreadable: {exc}",
            ) from exc


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval-model-sweep",
        description=(
            "Sweep an agent's fixtures across candidate models; report a "
            "scored winner with effect size (KEEP_PIN / DROP_PIN)."
        ),
    )
    parser.add_argument("--agent", required=True, type=_agent_name_arg)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument(
        "--models",
        required=True,
        help=(
            "comma-separated candidate model ids; the default model is added "
            "automatically as the comparison anchor"
        ),
    )
    parser.add_argument("--default-model", default=DEFAULT_MODEL)
    parser.add_argument("--n-runs", type=int, default=3)
    parser.add_argument(
        "--min-effect",
        type=float,
        default=DEFAULT_MIN_EFFECT,
        help=(
            f"minimum recall lead over the default to justify a pin (default {DEFAULT_MIN_EFFECT})"
        ),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--provider", default=None)
    parser.add_argument(
        "--child-timeout",
        type=float,
        default=DEFAULT_CHILD_TIMEOUT_S,
        help=(
            "per-model wall-clock timeout in seconds for the base evaluator "
            f"child process (default {DEFAULT_CHILD_TIMEOUT_S}); a timed-out "
            "child fails the sweep as EXTERNAL rather than hanging"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="path for the JSON sweep artifact (default: under the reports dir)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate inputs and print the per-model plan; no API calls",
    )
    return parser


def _plan_lines(agent: str, fixtures: Path, models: list[str], n_runs: int) -> list[str]:
    lines = [
        f"sweep plan: agent={agent} fixtures={fixtures} n_runs={n_runs}",
        f"models ({len(models)}):",
    ]
    lines += [f"  - {m}" for m in models]
    return lines


def _default_output_path(agent: str) -> Path:
    stamp = _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Add a short random suffix so repeated sweeps of the same agent within
    # the same second do not silently overwrite each other's evidence.
    suffix = uuid.uuid4().hex[:8]
    return REPO_ROOT / REPORTS_DIR_TEMPLATE.format(agent=agent) / f"sweep-{stamp}-{suffix}.json"


def run_sweep(args: argparse.Namespace, runner: ModelEvalRunner | None = None) -> int:
    """Live path: evaluate each model via *runner*, decide, write artifact.

    ``runner`` is optional so callers can exercise the input-validation and
    ``--dry-run`` branches (which never touch it) without constructing one;
    the live loop below rejects a missing runner explicitly.
    """
    try:
        models = parse_models_arg(args.models, default_model=args.default_model)
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    unpriced = validate_models_priced(models)
    if unpriced:
        print(
            "error: no pricing rate for model(s): "
            + ", ".join(sorted(unpriced))
            + ". Add them to MODEL_PRICING_RATES_USD_PER_1K_TOKENS in "
            "scripts/eval/_eval_common.py (with a verified rate) before "
            "sweeping; the base evaluator refuses unpriced models (#2858).",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    if args.n_runs < 1:
        print(f"error: --n-runs must be >= 1 (got {args.n_runs})", file=sys.stderr)
        return EXIT_CONFIG

    if not math.isfinite(args.child_timeout) or args.child_timeout <= 0:
        print(
            f"error: --child-timeout must be a finite value > 0 (got {args.child_timeout:g})",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    if not args.fixtures.exists():
        print(f"error: fixtures path not found: {args.fixtures}", file=sys.stderr)
        return EXIT_CONFIG

    if args.dry_run:
        for line in _plan_lines(args.agent, args.fixtures, models, args.n_runs):
            print(line)
        return EXIT_OK

    if runner is None:
        print(
            "error: run_sweep reached live execution without a runner",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    results: list[ModelResult] = []
    for model_id in models:
        try:
            results.append(runner.run(model_id))
        except ChildRunError as exc:
            print(f"error: {exc}", file=sys.stderr)
            # Preserve the child's exit-code class per the repo contract
            # (1=logic, 2=config, 4=auth); any other child failure is
            # "external" (3) to the sweep.
            if exc.returncode in (EXIT_LOGIC, EXIT_CONFIG, EXIT_AUTH):
                return exc.returncode
            return EXIT_EXTERNAL

    try:
        decision = decide(
            results,
            default_model=args.default_model,
            min_effect=args.min_effect,
            seed=args.seed,
        )
    except SweepDecisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    report = build_report(
        agent=args.agent,
        fixtures_sha=next((r.fixture_set_sha for r in results if r.fixture_set_sha), ""),
        results=results,
        decision=decision,
        min_effect=args.min_effect,
        seed=args.seed,
    )
    output = args.output or _default_output_path(args.agent)
    # Emit the verdict before persisting so an artifact-write failure does not
    # also cost the operator the KEEP/DROP result.
    print(f"{decision.decision}: {decision.reason}")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        print(f"error: could not write artifact to {output}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL

    print(f"artifact: {output}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    runner = SubprocessModelEvalRunner(
        agent=args.agent,
        fixtures=args.fixtures,
        n_runs=args.n_runs,
        provider=args.provider,
        child_timeout=args.child_timeout,
    )
    return run_sweep(args, runner)


if __name__ == "__main__":
    sys.exit(main())
