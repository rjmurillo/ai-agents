#!/usr/bin/env python3
# ruff: noqa: E402
"""Report canonical, generated, always-on, and per-fixture instruction bytes.

Issue #5400. One deterministic command answers: how many bytes of authored
instruction context exist, how many are generated mirrors, what loads on every
task, and what each of six routing fixtures (F1 to F6) loads. It reads the tree
on demand; nothing in this output is meant to be copied into durable prose.

Reused rather than rebuilt:
    * always-on bytes: ``control_plane_baseline.always_loaded`` (the existing counter);
    * token estimate: ``token_budget.estimate_token_count``;
    * canonical versus generated classification and skill/agent dependencies:
      ``check_capability_graph`` (ADR-110);
    * the ratchet convention: ceilings in ``instruction_budget_constants`` that
      may only fall (``test_instruction_ceiling_ratchet.py``).

Not in scope (issue #5400 rescope of 2026-09-24): duplicated-normative-byte
metrics (blocked on #5397) and runtime performance correlation (#5422 to #5426).

Exit codes follow ADR-035:
    0 - Success (or a ceiling breach outside ``--ci``)
    1 - Logic error (a fixture exceeds its ceiling, ``--ci`` only)
    2 - Configuration error (unreadable tree, unknown fixture entrypoint)
    3 - External error (git could not resolve or read ``--base-ref``)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_PACKAGE_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _VALIDATION_PACKAGE_SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.instruction_budget_constants import FIXTURE_CEILINGS_BYTES
from scripts.validation.instruction_bytes_corpus import CorpusError, group_summary, measure_corpus
from scripts.validation.instruction_bytes_delta import (
    DEFAULT_GROWTH_THRESHOLD_BYTES,
    GitError,
    compute_delta,
    materialize_base,
    resolve_ref,
)
from scripts.validation.instruction_bytes_fixtures import (
    FIXTURES,
    SOURCES,
    FixtureResult,
    load_always_on,
    load_graph,
    measure_fixture,
)
from scripts.validation.instruction_bytes_report import format_table
from scripts.validation.instruction_bytes_types import summarize, top_contributors

__all__ = ["build_parser", "build_report", "fixture_breaches", "main"]

ESTIMATOR = "scripts.validation.token_budget.estimate_token_count"


def _fixture_entry(result: FixtureResult, top: int) -> dict[str, Any]:
    files = result.files
    by_source = {s: sum(f.size_bytes for f in files if f.source == s) for s in SOURCES}
    ceiling = FIXTURE_CEILINGS_BYTES.get(result.fixture.fixture_id)
    return {
        "name": result.fixture.name,
        "edited_path": result.fixture.edited_path,
        "skills": list(result.fixture.skills),
        "agents": list(result.fixture.agents),
        "artifacts": len(files),
        **summarize(files),
        "bytes_by_source": by_source,
        "ceiling_bytes": ceiling,
        "top_contributors": top_contributors(files, top),
        "findings": list(result.findings),
    }


def build_report(repo_root: Path, top: int = 10, tolerate_missing: bool = False) -> dict[str, Any]:
    """Measure the tree at ``repo_root``.

    ``tolerate_missing`` is for a base revision: a fixture whose entrypoint did
    not exist there is recorded as an ``error`` entry instead of aborting, so a
    PR that introduces a skill a fixture names can still be compared.
    """
    canonical, generated = measure_corpus(repo_root)
    always_on = load_always_on(repo_root)
    graph = load_graph(repo_root)
    fixtures: dict[str, Any] = {}
    for fixture in FIXTURES:
        try:
            result = measure_fixture(repo_root, fixture, graph, always_on)
        except CorpusError as exc:
            if not tolerate_missing:
                raise
            fixtures[fixture.fixture_id] = {"name": fixture.name, "error": str(exc)}
            continue
        fixtures[fixture.fixture_id] = _fixture_entry(result, top)
    generated_summary = group_summary(generated)
    every_canonical = [f for files in canonical.values() for f in files]
    return {
        "estimator": ESTIMATOR,
        "canonical": {
            **group_summary(canonical),
            "top_contributors": top_contributors(every_canonical, top),
            "paths": {f.path: f.size_bytes for f in every_canonical},
        },
        "generated": {
            "families": generated_summary["groups"],
            "total": generated_summary["total"],
            "note": "generated mirrors are excluded from canonical totals",
        },
        "always_on": {
            harness: {"files": len(data["files"]), "bytes": data["bytes"], "tokens": data["tokens"]}
            for harness, data in always_on.harnesses.items()
        },
        "fixtures": fixtures,
        "findings": sorted([*always_on.findings, *graph.defects]),
    }


def fixture_breaches(report: dict[str, Any]) -> list[str]:
    """Name every fixture whose activated bytes exceed its ceiling."""
    return [
        f"{fid}: {data['bytes']} bytes exceeds ceiling {data['ceiling_bytes']}"
        for fid, data in sorted(report["fixtures"].items())
        if data.get("ceiling_bytes") is not None and data["bytes"] > data["ceiling_bytes"]
    ]


def _measure_base(repo_root: Path, ref: str, top: int) -> tuple[str, dict[str, Any]]:
    sha = resolve_ref(repo_root, ref)
    with tempfile.TemporaryDirectory(prefix="instruction-bytes-base-") as tmp:
        materialize_base(repo_root, sha, Path(tmp))
        try:
            return sha, build_report(Path(tmp), top, tolerate_missing=True)
        except CorpusError as exc:
            raise CorpusError(f"base {ref} ({sha[:12]}) cannot be measured: {exc}") from exc


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got '{value}'") from None
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"must be non-negative, got {parsed}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report canonical, generated, always-on, and per-fixture instruction bytes.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("REPO_PATH", "."),
        help="Repository root (env: REPO_PATH, default: '.')",
    )
    parser.add_argument(
        "--format", choices=["table", "json"], default="table", dest="output_format"
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        metavar="REF",
        help="Also measure this git revision and report the delta",
    )
    parser.add_argument(
        "--top", type=_non_negative_int, default=10, help="Top contributors to list"
    )
    parser.add_argument(
        "--growth-threshold-bytes",
        type=_non_negative_int,
        default=DEFAULT_GROWTH_THRESHOLD_BYTES,
        metavar="BYTES",
        help="Warn when always-on or fixture bytes grow past this versus --base-ref",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="Exit 1 when a fixture exceeds its ceiling (env: CI)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = build_parser().parse_args(argv)
    repo_root = Path(args.path).resolve()
    if not repo_root.is_dir():
        print(f"Error: path is not a directory: {args.path}", file=sys.stderr)
        return 2
    try:
        report = build_report(repo_root, args.top)
        if args.base_ref is not None:
            sha, base = _measure_base(repo_root, args.base_ref, args.top)
            delta = compute_delta(base, report, args.growth_threshold_bytes, args.top)
            report["delta"] = {"base_ref": args.base_ref, "base_sha": sha, **delta}
    except CorpusError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except GitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3
    breaches = fixture_breaches(report)
    report["ceiling_breaches"] = breaches
    print(json.dumps(report, indent=2) if args.output_format == "json" else format_table(report))
    return 1 if breaches and args.ci else 0


if __name__ == "__main__":
    raise SystemExit(main())
