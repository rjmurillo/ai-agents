#!/usr/bin/env python3
"""Eval Agent vs. Baseline runner (T4-1 scaffolding only).

DESIGN-004 §5.1 (CLI Entry Point), §5.2 (FixtureValidator). T4-1 implements:
- Argument parsing
- Fixture loading + validation (FixtureValidator)
- Plan + dry-run cost printout via PlanRunner
- Schema-version guard

T4-2 wires AnthropicAPIAdapter and RunPersistence into the live run path.
T4-3 wires ReportAggregator and ReportWriter. Until then `--dry-run` is the
only working mode; the live path prints a placeholder and exits 0.

Exit codes (AGENTS.md):
    0 = success
    1 = logic error
    2 = config / fixture invalid
    3 = external (API) failure
    4 = auth
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from _eval_agent_types import (
    SCHEMA_VERSION,
    Assertion,
    AssertionKind,
    Fixture,
    FixtureValidationError,
    SchemaVersionError,
)
from _plan_runner import PlanRunner, UnsupportedModelError

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
        help="run id (default: ISO8601 + UUID4); used by T4-2 persistence",
    )
    parser.add_argument(
        "--resume",
        default=None,
        metavar="RUN_ID",
        help="resume an interrupted run (T4-2 wires the skip-on-existing logic)",
    )
    return parser


def _print_plan(plan_lines: list[str]) -> None:
    for line in plan_lines:
        print(line)


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

    print("T4-2 not yet implemented (live run path)", file=sys.stderr)
    print(f"agent={args.agent} run_id={args.run_id} resume={args.resume}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
