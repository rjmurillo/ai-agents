#!/usr/bin/env python3
"""Plan, and only when told to run, the live reduced-control experiment (issue #5768).

Runs the #5425 routing corpus under two instruction-control configurations
on the Claude or Codex harness and writes `OutcomeRecord` JSONL that
`eval_durable_outcome.py` reads. See `_durable_live.py` for why this is not the
#6031 routing runner and which record fields are measured or proxies.

    eval_durable_live.py                                   # dry run, zero spend
    eval_durable_live.py --live --use-stored-login --output-dir DIR
    eval_durable_live.py --harness codex --live --use-stored-login --output-dir DIR

The default is a dry run: it prints the control sizes and the launch upper
bound, and starts no process. `--live` spends, and also needs
`--use-stored-login`, the operator's acknowledgement that the run bills to the
Claude or Codex login stored on this machine. No credential file is read here.

Exit codes (AGENTS.md): 0 every task produced a record. 1 the comparison is
WORSE or UNVERIFIED. 2 invalid arguments, corpus, or control files. 3 a
harness failure left a task without a record. 4 `--live` without
`--use-stored-login`, or the harness CLI is not on PATH.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from _durable_live import (
    CONTROLS,
    DEFAULT_MAX_TURNS,
    HARNESSES,
    ExperimentResult,
    InvocationBudget,
    LiveRunError,
    RunSettings,
    control_text,
    max_invocations,
    run_experiment,
)
from _durable_live_record import record_to_row
from _durable_outcome import build_report, compare
from _outcome_record import DurableOutcomeError
from _routing_scenario import RoutingCorpusError, Scenario, load_corpus, load_extension_corpus

EXIT_OK = 0
EXIT_UNVERIFIED_OR_WORSE = 1
EXIT_CONFIG = 2
EXIT_HARNESS_FAILURE = 3
EXIT_AUTH = 4

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPO_ROOT / "evals" / "routing-benchmark" / "scenarios"
BASELINE_CONTROL = "current"
CANDIDATE_CONTROL = "reduced"
_FAILING_RESULTS = frozenset({"WORSE", "UNVERIFIED"})
DEFAULT_MODEL = {"claude": "haiku", "codex": "gpt-5.6-luna"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--extension-corpus",
        type=Path,
        help="directory of post_integration_regression scenarios, run after --corpus",
    )
    parser.add_argument("--harness", choices=HARNESSES, default="claude")
    parser.add_argument(
        "--model",
        help=f"model passed to the harness (default: {DEFAULT_MODEL['claude']} for claude, "
        f"{DEFAULT_MODEL['codex']} for codex)",
    )
    parser.add_argument("--effort", default="low")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument("--retry-budget", type=int, default=1, help="correction rounds per task")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--first-repeat", type=int, default=0, help="index of the first repeat")
    parser.add_argument("--max-invocations", type=int, default=60, help="hard launch cap")
    parser.add_argument("--tasks", help="comma-separated scenario ids to run (default: all)")
    parser.add_argument("--controls", help="comma-separated controls to run (default: all)")
    parser.add_argument("--live", action="store_true", help="spend: launch the harness CLI")
    parser.add_argument("--use-stored-login", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    return parser


def _split(value: str | None) -> list[str] | None:
    return None if value is None else [item.strip() for item in value.split(",") if item.strip()]


def _select(scenarios: list[Scenario], tasks: str | None) -> list[Scenario]:
    wanted = _split(tasks)
    if wanted is None:
        return scenarios
    known = {s.scenario_id: s for s in scenarios}
    missing = [task for task in wanted if task not in known]
    if missing or not wanted:
        raise LiveRunError(f"--tasks names no known scenario: {missing or 'empty list'}")
    return [known[task] for task in wanted]


def _select_controls(controls: str | None) -> list[str]:
    wanted = _split(controls)
    if wanted is None:
        return list(CONTROLS)
    unknown = [name for name in wanted if name not in CONTROLS]
    if unknown or not wanted:
        raise LiveRunError(f"--controls names no known control: {unknown or 'empty list'}")
    return wanted


def _validate(args: argparse.Namespace) -> str | None:
    if args.live and args.output_dir is None:
        return "--live requires --output-dir"
    if args.output_dir is not None and not args.live:
        return "--output-dir is only valid with --live"
    for name in ("max_turns", "repeats", "max_invocations"):
        if getattr(args, name) < 1:
            return f"--{name.replace('_', '-')} must be at least 1"
    if args.first_repeat < 0:
        return "--first-repeat must not be negative"
    if args.retry_budget < 0:
        return "--retry-budget must not be negative"
    return None


def _git_head(repo_root: Path) -> str:
    done = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def plan_report(
    scenarios: Sequence[Scenario], texts: Mapping[str, str], args: argparse.Namespace
) -> dict[str, object]:
    bound = max_invocations(len(scenarios), len(texts), args.repeats, args.retry_budget)
    return {
        "mode": "dry-run",
        "model_calls": 0,
        "harness": args.harness,
        "model": args.model or DEFAULT_MODEL[args.harness],
        "tasks": [s.scenario_id for s in scenarios],
        "controls": {
            name: {"files": list(CONTROLS[name]), "bytes": len(text.encode("utf-8"))}
            for name, text in texts.items()
        },
        "repeats": args.repeats,
        "first_repeat": args.first_repeat,
        "retry_budget": args.retry_budget,
        "max_invocations": bound,
        "cap": args.max_invocations,
        "within_cap": bound <= args.max_invocations,
    }


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), "utf-8")


def _analyze(result: ExperimentResult, out: Path) -> tuple[dict[str, object], int]:
    """Write per-control reports and the matched comparison. Return (summary, exit code)."""
    summary: dict[str, object] = {}
    for control, records in result.records.items():
        _write_jsonl(out / f"{control}.jsonl", [record_to_row(r) for r in records])
        if records:
            report = build_report(records)
            (out / f"report-{control}.json").write_text(json.dumps(report, indent=2), "utf-8")
            summary[f"{control}_status"] = report["status"]
    if BASELINE_CONTROL not in result.records or CANDIDATE_CONTROL not in result.records:
        summary["comparison"] = "not run: a subset run holds one control"
        return summary, EXIT_OK
    base = result.records[BASELINE_CONTROL]
    cand = result.records[CANDIDATE_CONTROL]
    try:
        comparison = compare(base, cand)
    except DurableOutcomeError as exc:
        summary["comparison"] = f"refused: {exc}"
        return summary, EXIT_HARNESS_FAILURE if result.harness_failures else EXIT_CONFIG
    (out / "comparison.json").write_text(json.dumps(comparison, indent=2), "utf-8")
    summary["comparison"] = comparison["result"]
    return summary, EXIT_UNVERIFIED_OR_WORSE if comparison[
        "result"
    ] in _FAILING_RESULTS else EXIT_OK


def _codex_version() -> str:
    done = subprocess.run(
        ["codex", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        stdin=subprocess.DEVNULL,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def _effort_fields(args: argparse.Namespace, result: ExperimentResult) -> dict[str, object]:
    """Requested and observed effort. Verified only when the backend named it every time."""
    if args.harness == "claude":
        return {
            "effort_verified": False,
            "effort_observed": "unobservable: the claude stream does not report effort",
        }
    seen = sorted({e for i in result.invocations for e in i.facts.efforts})
    every = bool(result.invocations) and all(i.facts.efforts for i in result.invocations)
    return {
        "effort_verified": every and seen == [args.effort],
        "effort_observed": seen or "none: no backend frame named an effort",
    }


def _run_live(
    scenarios: Sequence[Scenario], texts: Mapping[str, str], args: argparse.Namespace
) -> int:
    model = args.model or DEFAULT_MODEL[args.harness]
    settings = RunSettings(
        model,
        args.effort,
        args.max_turns,
        args.retry_budget,
        harness=args.harness,
        cli_version=_codex_version() if args.harness == "codex" else "",
    )
    budget = InvocationBudget(args.max_invocations)
    result = run_experiment(
        scenarios,
        texts,
        settings,
        budget,
        repeats=args.repeats,
        first_repeat=args.first_repeat,
    )
    out: Path = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out / "invocations.jsonl", [i.summary() for i in result.invocations])
    summary, code = _analyze(result, out)
    summary.update(
        {
            "harness_scope": f"{args.harness} only, not cross-harness",
            "harness": args.harness,
            "commit": _git_head(args.repo_root),
            "requested_model": model,
            "requested_effort": args.effort,
            **_effort_fields(args, result),
            "first_repeat": args.first_repeat,
            "repeats": args.repeats,
            "launches": budget.used,
            "harness_failures": [list(item) for item in result.harness_failures],
            "control_bytes": {n: len(t.encode("utf-8")) for n, t in texts.items()},
        }
    )
    (out / "run-summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(json.dumps(summary, indent=2))
    return EXIT_HARNESS_FAILURE if result.harness_failures and code == EXIT_OK else code


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    problem = _validate(args)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        corpus = load_corpus(args.corpus)
        if args.extension_corpus is not None:
            corpus = [*corpus, *load_extension_corpus(args.extension_corpus)]
        scenarios = _select(corpus, args.tasks)
        names = _select_controls(args.controls)
        texts = {name: control_text(args.repo_root, name) for name in names}
    except (RoutingCorpusError, LiveRunError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if not args.live:
        print(json.dumps(plan_report(scenarios, texts, args), indent=2))
        return EXIT_OK
    if not args.use_stored_login:
        message = f"--live needs --use-stored-login (bills to the stored {args.harness} login)"
        print(f"error: {message}", file=sys.stderr)
        return EXIT_AUTH
    if shutil.which(args.harness) is None:
        print(f"error: {args.harness} is not on PATH", file=sys.stderr)
        return EXIT_AUTH
    try:
        return _run_live(scenarios, texts, args)
    except LiveRunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_HARNESS_FAILURE


if __name__ == "__main__":
    sys.exit(main())
