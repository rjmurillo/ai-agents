#!/usr/bin/env python3
"""Eval Agent vs. Baseline runner.

DESIGN-004 §5. Pipeline:

    CLI -> FixtureValidator -> PlanRunner ->
        (dry-run path: print plan, exit)
    or
        (live path: AnthropicAPIAdapter + ScoringEngine + RunPersistence)

T4-1 shipped scaffolding (validator, plan runner, scoring engine).
T4-2 wires the live run loop with retry, idempotency, and `--resume`.
T4-3 adds report aggregation + writing.

Exit codes (AGENTS.md):
    0 = success
    1 = logic error / duplicate run / flakiness halt
    2 = config / fixture invalid
    3 = external (API) failure
    4 = auth
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from _eval_agent_types import (
    SCHEMA_VERSION,
    Assertion,
    AssertionKind,
    Fixture,
    FixtureValidationError,
    RunRecord,
    SchemaVersionError,
)
from _eval_api_adapter import AnthropicAPIAdapter, APICallResult
from _plan_runner import PlanRunner, UnsupportedModelError
from _run_persistence import DuplicateRunError, RunPersistence
from _scoring_engine import build_default_engine

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_N_RUNS = 3
ALLOWED_PROVENANCE = frozenset(
    {"synthetic", "public-cve", "paraphrased-from-public"}
)
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_:-]{0,63}$")

REPO_ROOT = Path(__file__).resolve().parents[2]

# DESIGN-004 §Technology Decisions: deliberately naive baseline. Same
# response shape as the agent so the scoring engine is symmetric. Any
# observed lift is attributable to specialization in the agent prompt,
# not to task framing.
BASELINE_PROMPT = (
    "Review the following input. Respond with one word: IDENTIFY, OK, or "
    "ESCALATE. Then explain in <=80 words."
)
BASELINE_PROMPT_REF = "<baseline>"

# The agent prompt is sourced from the canonical template path. SHA is
# computed from the file content (UTF-8, no trailing newline trim).
AGENT_PROMPT_REF_TEMPLATE = "templates/agents/{agent}.shared.md"

# Error rate cap (REQ-004 AC-3). Above this, the runner exits 1 before
# generating a report. Expressed as the fraction of successful records.
MAX_ERROR_RATE = 0.10

RUNS_DIR_TEMPLATE = "evals/security-spike/runs/{run_id}"


# ---------------------------------------------------------------------------
# FixtureValidator (DESIGN-004 §5.2, REQ-004 AC-4)
# ---------------------------------------------------------------------------


class FixtureValidator:
    """Load and validate fixtures before any API call."""

    @staticmethod
    def validate_fixtures(paths: list[Path]) -> list[Fixture]:
        if not paths:
            raise FixtureValidationError("no fixtures supplied")
        fixtures: list[Fixture] = []
        for path in paths:
            fixtures.append(FixtureValidator._validate_one(path))
        return fixtures

    @staticmethod
    def _validate_one(path: Path) -> Fixture:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise FixtureValidationError(
                f"{path.name}: cannot parse JSON ({exc})"
            ) from exc

        if not isinstance(data, dict):
            raise FixtureValidationError(f"{path.name}: top-level must be a JSON object")

        FixtureValidator._check_schema_version(path, data)
        fixture_id = FixtureValidator._require_str(path, data, "id")
        fixture_input = FixtureValidator._require_str(path, data, "input")
        provenance = FixtureValidator._require_provenance(path, data)
        assertions = FixtureValidator._require_assertions(path, fixture_id, data)
        tags = FixtureValidator._validate_tags(path, fixture_id, data)

        return Fixture(
            id=fixture_id,
            input=fixture_input,
            provenance=provenance,  # type: ignore[arg-type]
            assertions=assertions,
            tags=tags,
            schema_version=SCHEMA_VERSION,
        )

    @staticmethod
    def _check_schema_version(path: Path, data: dict[str, Any]) -> None:
        version = data.get("schemaVersion")
        if version != SCHEMA_VERSION:
            raise SchemaVersionError(
                f"{path.name}: schemaVersion must be {SCHEMA_VERSION}, got {version!r}"
            )

    @staticmethod
    def _require_str(path: Path, data: dict[str, Any], field: str) -> str:
        value = data.get(field)
        if not isinstance(value, str) or not value:
            raise FixtureValidationError(
                f"{path.name}: missing or empty required field '{field}'"
            )
        return value

    @staticmethod
    def _require_provenance(path: Path, data: dict[str, Any]) -> str:
        provenance = data.get("provenance")
        if provenance not in ALLOWED_PROVENANCE:
            raise FixtureValidationError(
                f"{path.name}: provenance must be one of {sorted(ALLOWED_PROVENANCE)}, "
                f"got {provenance!r}"
            )
        return provenance  # type: ignore[return-value]

    @staticmethod
    def _require_assertions(
        path: Path, fixture_id: str, data: dict[str, Any]
    ) -> list[Assertion]:
        raw = data.get("assertions")
        if not isinstance(raw, list) or not raw:
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): 'assertions' must be a non-empty list"
            )
        result: list[Assertion] = []
        for index, item in enumerate(raw):
            result.append(
                FixtureValidator._validate_assertion(path, fixture_id, index, item)
            )
        return result

    @staticmethod
    def _validate_assertion(
        path: Path, fixture_id: str, index: int, item: Any
    ) -> Assertion:
        if not isinstance(item, dict):
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): assertions[{index}] must be an object"
            )
        kind_raw = item.get("kind")
        try:
            kind = AssertionKind(kind_raw)
        except ValueError as exc:
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): assertions[{index}].kind={kind_raw!r} "
                f"must be one of {[k.value for k in AssertionKind]}"
            ) from exc
        pattern = item.get("pattern")
        expected_value = item.get("expected_value")
        try:
            return Assertion(
                kind=kind,
                pattern=pattern if isinstance(pattern, str) else None,
                expected_value=(
                    expected_value if isinstance(expected_value, str) else None
                ),
            )
        except ValueError as exc:
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): assertions[{index}] {exc}"
            ) from exc

    @staticmethod
    def _validate_tags(
        path: Path, fixture_id: str, data: dict[str, Any]
    ) -> list[str]:
        raw = data.get("tags", [])
        if not isinstance(raw, list):
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): 'tags' must be a list"
            )
        for tag in raw:
            if not isinstance(tag, str) or not TAG_RE.match(tag):
                raise FixtureValidationError(
                    f"{path.name} ({fixture_id}): invalid tag {tag!r}; "
                    f"must match {TAG_RE.pattern}"
                )
        return list(raw)


# ---------------------------------------------------------------------------
# Helpers shared by run loop and report (T4-3 will reuse).
# ---------------------------------------------------------------------------


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_agent_prompt(agent: str) -> tuple[str, str]:
    """Return (prompt_text, prompt_ref). Raises FileNotFoundError on miss."""
    rel = AGENT_PROMPT_REF_TEMPLATE.format(agent=agent)
    path = REPO_ROOT / rel
    if not path.exists():
        raise FileNotFoundError(
            f"agent prompt not found at {path} (looked for {agent}.shared.md)"
        )
    return path.read_text(encoding="utf-8"), rel


def _fixture_sha(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def _generate_run_id() -> str:
    """ISO8601 compact timestamp + UUID4 short tail. Collision-free by construction."""
    now = _dt.datetime.now(_dt.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"{stamp}-{suffix}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_fixture_paths(fixtures_dir: Path) -> list[Path]:
    if not fixtures_dir.exists() or not fixtures_dir.is_dir():
        raise FileNotFoundError(f"no fixtures found at {fixtures_dir}")
    paths = sorted(fixtures_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"no fixtures found at {fixtures_dir}")
    return paths


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval-agent-vs-baseline",
        description="Eval the agent prompt vs. a generic baseline prompt.",
    )
    parser.add_argument("--agent", required=True, help="agent name (e.g. security)")
    parser.add_argument(
        "--fixtures",
        required=True,
        type=Path,
        help="directory of fixture JSON files",
    )
    parser.add_argument(
        "--n-runs",
        type=int,
        default=DEFAULT_N_RUNS,
        help=f"runs per (fixture, variant) (default: {DEFAULT_N_RUNS})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate fixtures and print plan; no API calls",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="run id (default: ISO8601 + UUID4); used by RunPersistence",
    )
    parser.add_argument(
        "--resume",
        default=None,
        metavar="RUN_ID",
        help="resume an interrupted run; skip already-completed triples",
    )
    return parser


def _print_plan(plan_lines: list[str]) -> None:
    for line in plan_lines:
        print(line)


def _build_prompt(variant: str, agent_prompt: str, fixture_input: str) -> tuple[str, str]:
    """Compose the (system, user) message pair for a variant.

    Agent variant: system = agent prompt; user = fixture input.
    Baseline variant: system = baseline prompt; user = fixture input.
    Returns (system, user_prompt) so token estimates split cleanly.
    """
    if variant == "agent":
        return agent_prompt, fixture_input
    return BASELINE_PROMPT, fixture_input


def _resolve_prompt_metadata(
    variant: str, agent_prompt: str, agent_prompt_ref: str
) -> tuple[str, str]:
    """(prompt_sha, prompt_ref) for the variant. Same SHA convention for both."""
    if variant == "agent":
        return _sha256_text(agent_prompt), agent_prompt_ref
    return _sha256_text(BASELINE_PROMPT), BASELINE_PROMPT_REF


def _execute_one(
    *,
    fixture: Fixture,
    fixture_path: Path,
    variant: str,
    run_index: int,
    model_id: str,
    agent_prompt: str,
    agent_prompt_ref: str,
    adapter: AnthropicAPIAdapter,
    scoring_engine,
) -> RunRecord:
    """Run one (fixture, variant, run_index) call and score the result."""
    system, user = _build_prompt(variant, agent_prompt, fixture.input)
    prompt_sha, prompt_ref = _resolve_prompt_metadata(
        variant, agent_prompt, agent_prompt_ref
    )
    fixture_sha = _fixture_sha(fixture_path)

    api_result: APICallResult = adapter.call_model(
        prompt=user,
        model_id=model_id,
        fixture_id=fixture.id,
        variant=variant,
        run_index=run_index,
        system=system,
    )

    if api_result.outcome == "success" and api_result.raw_response is not None:
        scored = scoring_engine.score_all(fixture.assertions, api_result.raw_response)
    else:
        # Record the assertion shape with passed=False so downstream
        # aggregation can decide to count or exclude per AC-3.
        scored = [
            type_assertion_failed(a) for a in fixture.assertions
        ]

    return RunRecord(
        fixture_id=fixture.id,
        variant=variant,  # type: ignore[arg-type]
        run_index=run_index,
        model_id=model_id,
        prompt_sha=prompt_sha,
        prompt_ref=prompt_ref,
        fixture_sha=fixture_sha,
        raw_response=api_result.raw_response,
        assertions=scored,
        outcome=api_result.outcome,
        latency_ms=api_result.latency_ms,
        tokens_in=api_result.tokens_in,
        tokens_out=api_result.tokens_out,
        error_category=api_result.error_category,
        attempts=api_result.attempts,
    )


def type_assertion_failed(assertion: Assertion):
    """Construct an AssertionResult representing 'not scored, treat as failed'.

    Used when the API call errored; the caller decides via outcome whether
    to count this in `recall_with_errors` vs `recall_excluding_errors`.
    """
    from _eval_agent_types import AssertionResult

    return AssertionResult(
        kind=assertion.kind,
        pattern=assertion.pattern,
        expected_value=assertion.expected_value,
        passed=False,
        extracted=None,
    )


def _run_live(
    *,
    args: argparse.Namespace,
    fixtures: list[Fixture],
    fixture_paths: list[Path],
    plan,
) -> int:
    """Execute the live run loop. Returns exit code."""
    try:
        agent_prompt, agent_prompt_ref = _read_agent_prompt(args.agent)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if args.resume and args.run_id and args.run_id != args.resume:
        print(
            "error: --run-id and --resume cannot specify different ids",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    run_id = args.resume or args.run_id or _generate_run_id()
    run_dir = REPO_ROOT / RUNS_DIR_TEMPLATE.format(run_id=run_id)

    try:
        persistence = RunPersistence(run_dir, resume=bool(args.resume))
    except DuplicateRunError as exc:
        # Bad existing JSONL detected at startup.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LOGIC

    fixture_path_by_id = {f.id: p for f, p in zip(fixtures, fixture_paths)}
    adapter = AnthropicAPIAdapter()
    engine = build_default_engine()

    error_count = 0
    total_records = 0

    for fixture in plan.fixtures:
        fixture_path = fixture_path_by_id[fixture.id]
        for variant in plan.variants:
            for run_index in range(plan.n_runs):
                if persistence.is_completed(fixture.id, variant, run_index):
                    # Already-complete triples in resume mode are skipped silently
                    # (REQ-004 AC-9 resume contract). Counted as one record for
                    # error-rate accounting since the prior run already scored it.
                    total_records += 1
                    continue
                record = _execute_one(
                    fixture=fixture,
                    fixture_path=fixture_path,
                    variant=variant,
                    run_index=run_index,
                    model_id=plan.model_id,
                    agent_prompt=agent_prompt,
                    agent_prompt_ref=agent_prompt_ref,
                    adapter=adapter,
                    scoring_engine=engine,
                )
                try:
                    persistence.write_record(record)
                except DuplicateRunError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return EXIT_LOGIC
                if record.outcome == "error":
                    error_count += 1
                total_records += 1

    if total_records > 0:
        error_rate = error_count / total_records
        if error_rate > MAX_ERROR_RATE:
            print(
                json.dumps(
                    {
                        "level": "error",
                        "message": "error rate exceeds 10%; halting before report",
                        "error_count": error_count,
                        "total_records": total_records,
                        "error_rate": round(error_rate, 4),
                    }
                ),
                file=sys.stderr,
            )
            return EXIT_LOGIC

    # T4-3 wires the report aggregator + writer here.
    print(
        json.dumps(
            {
                "level": "info",
                "message": "run complete (report generation lands in T4-3)",
                "run_id": run_id,
                "run_dir": str(run_dir),
                "written": persistence.written_count(),
                "skipped_resume": persistence.skipped_count(),
                "errors": error_count,
            }
        ),
        file=sys.stderr,
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        paths = _load_fixture_paths(args.fixtures)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        fixtures = FixtureValidator.validate_fixtures(paths)
    except (FixtureValidationError, SchemaVersionError) as exc:
        print(f"fixture validation failed: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        plan = PlanRunner.build_plan(
            fixtures=fixtures,
            model_id=args.model,
            n_runs=args.n_runs,
        )
    except (ValueError, UnsupportedModelError) as exc:
        print(f"plan error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if args.dry_run:
        _print_plan(PlanRunner.format_plan_lines(plan))
        return EXIT_OK

    return _run_live(args=args, fixtures=fixtures, fixture_paths=paths, plan=plan)


if __name__ == "__main__":
    sys.exit(main())
