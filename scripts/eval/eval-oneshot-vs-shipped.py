#!/usr/bin/env python3
"""One-shot-vs-shipped benchmark CLI (issue #2788).

Point an agent at a closed bug plus its full issue/PR discourse, withhold the
merged fix, have the agent reason a fix and set its own acceptance, then grade
the agent fix against what shipped with an LLM judge. The grading logic lives in
`_oneshot_bench_core`; this file owns argument parsing, the API transport, and
report writing.

Spend boundary: `--dry-run` validates fixtures and prints the call plan with
ZERO API spend, mirroring the main harness's no-spend path. A live run calls the
model twice per fixture (agent + judge) and requires `ANTHROPIC_API_KEY`.

Exit codes (AGENTS.md): 0 ok, 2 config (bad path, malformed fixture, missing
credentials, report write failure), 3 external (API failure during a live run).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_DIR.parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from _anthropic_api import call_api as _call_api  # noqa: E402
from _anthropic_api import load_api_key as _load_api_key  # noqa: E402
from _oneshot_bench_core import (  # noqa: E402
    BenchmarkSummary,
    Fixture,
    FixtureError,
    FixtureResult,
    JudgeVerdict,
    aggregate,
    build_agent_prompt,
    build_judge_prompt,
    load_fixtures,
    parse_judge_response,
    select_hardest,
)


def _api_error_verdict(reason: str) -> JudgeVerdict:
    """Verdict for a run that never reached the judge (transport failed).

    `judge_failed` stays False: the judge was never asked, so this is an API
    error, not a judge-parse failure. The grade is NONE because no fix was
    graded. Conflating the two would double-count one transport error as both
    `api_errors` and `judge_failures` in the aggregate.
    """
    return JudgeVerdict("NONE", (), (), reason, judge_failed=False)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

DEFAULT_MODEL = "claude-sonnet-4-6"
_AGENT_MAX_TOKENS = 1500
_JUDGE_MAX_TOKENS = 600
_DEFAULT_FIXTURES = Path("evals/oneshot-vs-shipped/corpus")


def _resolve_repo_child(path: Path, *, arg_name: str, require_dir: bool) -> Path:
    """Resolve a CLI path under the repository root, rejecting traversal."""
    candidate = path if path.is_absolute() else _REPO_ROOT / path
    try:
        resolved = candidate.expanduser().resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"{arg_name} {path} is not a valid path: {exc}") from exc
    repo_root = _REPO_ROOT.resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"{arg_name} {path} is outside repository root")
    if require_dir and not resolved.is_dir():
        raise ValueError(f"{arg_name} {path} is not a directory")
    return resolved


def grade_fixture(
    fixture: Fixture, *, api_key: str, model: str
) -> FixtureResult:
    """Run one fixture end to end: agent proposes, judge grades.

    A transport failure on either call is caught and recorded as an errored
    result (the harness continues to the next fixture) rather than aborting the
    whole run; the summary surfaces `api_errors` so a half-broken run cannot
    read as a clean score.
    """
    try:
        agent_fix = _call_api(
            api_key,
            [{"role": "user", "content": build_agent_prompt(fixture)}],
            model=model,
            max_tokens=_AGENT_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 - transport boundary, recorded not raised
        return FixtureResult(
            fixture_id=fixture.id,
            issue_number=fixture.issue_number,
            difficulty=fixture.difficulty,
            verdict=_api_error_verdict(f"agent call failed: {exc}"),
            error=f"agent call failed: {exc}",
        )
    try:
        judge_raw = _call_api(
            api_key,
            [{"role": "user", "content": build_judge_prompt(fixture, agent_fix)}],
            model=model,
            max_tokens=_JUDGE_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 - transport boundary, recorded not raised
        return FixtureResult(
            fixture_id=fixture.id,
            issue_number=fixture.issue_number,
            difficulty=fixture.difficulty,
            verdict=_api_error_verdict(f"judge call failed: {exc}"),
            agent_fix=agent_fix,
            error=f"judge call failed: {exc}",
        )
    return FixtureResult(
        fixture_id=fixture.id,
        issue_number=fixture.issue_number,
        difficulty=fixture.difficulty,
        verdict=parse_judge_response(judge_raw),
        agent_fix=agent_fix,
    )


def run_live(
    fixtures: list[Fixture], *, api_key: str, model: str
) -> BenchmarkSummary:
    results = [grade_fixture(f, api_key=api_key, model=model) for f in fixtures]
    return aggregate(fixtures, results)


def summary_to_json(summary: BenchmarkSummary, *, model: str) -> dict[str, object]:
    return {
        "model": model,
        "verdict": summary.verdict,
        "total": summary.total,
        "full": summary.full,
        "partial": summary.partial,
        "none": summary.none,
        "same_or_better_rate": round(summary.same_or_better_rate, 4),
        "edges_named": summary.edges_named,
        "edges_caught": summary.edges_caught,
        "edge_catch_rate": round(summary.edge_catch_rate, 4),
        "judge_failures": summary.judge_failures,
        "api_errors": summary.api_errors,
        "per_fixture": [
            {
                "fixture_id": r.fixture_id,
                "issue_number": r.issue_number,
                "difficulty": r.difficulty,
                "grade": r.verdict.grade,
                "edges_caught": list(r.verdict.edges_caught),
                "edges_missed": list(r.verdict.edges_missed),
                "reasoning": r.verdict.reasoning,
                "error": r.error,
            }
            for r in summary.per_fixture
        ],
    }


def summary_to_human(summary: BenchmarkSummary, *, model: str) -> str:
    lines = [
        f"One-shot-vs-shipped benchmark ({model}): {summary.verdict}",
        f"  graded {summary.total} fixture(s): "
        f"FULL={summary.full} PARTIAL={summary.partial} NONE={summary.none}",
        f"  same-or-better than shipped: {summary.same_or_better_rate:.0%}",
        f"  discourse edges caught: {summary.edges_caught}/{summary.edges_named} "
        f"({summary.edge_catch_rate:.0%})",
    ]
    if summary.judge_failures or summary.api_errors:
        lines.append(
            f"  harness errors: {summary.api_errors} API, "
            f"{summary.judge_failures} judge-parse"
        )
    for r in summary.per_fixture:
        tag = r.error or r.verdict.grade
        lines.append(f"  - {r.fixture_id} (d{r.difficulty}, #{r.issue_number}): {tag}")
    return "\n".join(lines)


def _dry_run_report(fixtures: list[Fixture], *, model: str) -> str:
    planned_calls = len(fixtures) * 2  # agent + judge per fixture
    lines = [
        f"DRY RUN ({model}): {len(fixtures)} fixture(s), "
        f"{planned_calls} planned API call(s), ZERO spend.",
    ]
    for f in fixtures:
        lines.append(
            f"  - {f.id} (difficulty {f.difficulty}, {f.source_repo}"
            f"#{f.issue_number}): {len(f.edges_named_in_discourse)} named edge(s)"
        )
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Grade an agent's one-shot fix against the shipped fix for closed "
            "bugs, using an LLM judge (issue #2788)."
        )
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=_DEFAULT_FIXTURES,
        help="Directory of fixture JSON files.",
    )
    parser.add_argument(
        "--hardest-n",
        type=int,
        default=None,
        help="Grade only the N hardest fixtures (default: all).",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Model id (default: {DEFAULT_MODEL})."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixtures and print the call plan with zero API spend.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write the JSON summary to this path (sample log accretion).",
    )
    parser.add_argument(
        "--output-format",
        choices=("human", "json"),
        default="human",
        help="Render the summary as text (default) or JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        fixtures_dir = _resolve_repo_child(
            args.fixtures, arg_name="--fixtures", require_dir=True
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        fixtures = select_hardest(load_fixtures(fixtures_dir), args.hardest_n)
    except FixtureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if not fixtures:
        print(f"error: no fixtures found under {fixtures_dir}", file=sys.stderr)
        return EXIT_CONFIG

    if args.dry_run:
        print(_dry_run_report(fixtures, model=args.model))
        return EXIT_OK

    try:
        api_key = _load_api_key()
    except Exception as exc:  # noqa: BLE001 - surface auth/config as exit 2
        print(f"error: cannot load API key: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    summary = run_live(fixtures, api_key=api_key, model=args.model)
    if args.report is not None:
        try:
            report_path = _resolve_repo_child(
                args.report, arg_name="--report", require_dir=False
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(summary_to_json(summary, model=args.model), indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"error: cannot write report {report_path}: {exc}", file=sys.stderr)
            return EXIT_CONFIG
    if args.output_format == "json":
        print(json.dumps(summary_to_json(summary, model=args.model), indent=2))
    else:
        print(summary_to_human(summary, model=args.model))
    # Any harness error (API transport or judge-parse) makes the run
    # inconclusive, so the exit code must be non-zero or a CI gate keying on it
    # would read INCONCLUSIVE_HARNESS_ERRORS as a pass.
    inconclusive = summary.api_errors or summary.judge_failures
    return EXIT_EXTERNAL if inconclusive else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
