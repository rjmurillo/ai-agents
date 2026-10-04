#!/usr/bin/env python3
"""Plan, and only when explicitly authorized run, the routing benchmark (issue #5424).

Thin CLI over `_routing_config.py`, `_routing_plan.py`, `_routing_run.py`, and
`_routing_live.py`. The default is a zero-spend dry run: it loads the strategy
config, the #5423 capability matrix, and the #5425 corpus, expands
strategy x scenario x harness, and prints every combination with its
eligibility class, the reason a combination was rejected, and which harness
pairs are matched. It makes no model call and starts no process.

    eval_routing_benchmark.py [--config F] [--matrix F] [--corpus D]
    eval_routing_benchmark.py --live --output RESULTS.jsonl

`--live` is the only way to spend. It fails closed: without a credential for
every harness in the plan the run stops with exit 4 before any process
starts, and it never falls back to the dry run's output as a result.

Exit codes (AGENTS.md): 0 the plan holds at least one planned combination, or a
live run finished with no harness failure. 1 nothing is plannable, or the plan
has problems (every combination rejected, or a config harness the matrix does
not classify). 2 invalid config, matrix, corpus, or arguments. 3 a live run hit
a harness failure. 4 `--live` without the credentials it needs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from _harness_capability import HarnessCapabilityError, load_matrix
from _routing_config import BenchmarkConfig, RoutingConfigError, load_config
from _routing_live import (
    BudgetExhaustedError,
    InvocationBudget,
    LiveBackend,
    LiveGateError,
    require_live_authorization,
)
from _routing_plan import Plan, PlanRow, build_plan
from _routing_result import RunStatus, result_to_dict
from _routing_run import run_planned
from _routing_scenario import RoutingCorpusError, Scenario, load_corpus

EXIT_OK = 0
EXIT_NOTHING_PLANNED = 1
EXIT_CONFIG = 2
EXIT_HARNESS_FAILURE = 3
EXIT_AUTH = 4

EXAMPLES = Path(__file__).resolve().parent / "examples"
DEFAULT_CONFIG = EXAMPLES / "routing-benchmark-config.json"
DEFAULT_MATRIX = EXAMPLES / "harness-capability-matrix.json"
DEFAULT_CORPUS = Path(__file__).resolve().parents[2] / "evals" / "routing-benchmark" / "scenarios"


def _row_dict(row: PlanRow) -> dict[str, object]:
    return {
        "scenario_id": row.scenario_id,
        "category": row.category,
        "difficulty": row.difficulty,
        "arm": row.arm,
        "harness": row.harness,
        "harness_version": row.harness_version,
        "status": row.status.value,
        "eligibility": row.eligibility,
        "reason": row.reason,
        "routes": [[r.role, r.route.model, r.route.effort] for r in row.routes],
        "harness_comparison": row.comparison.value,
        "harness_comparison_reason": row.comparison_reason,
        "pair_id": row.pair_id,
        "within_harness_group": row.within_harness_group,
        "contract_sha256": row.contract_sha,
    }


def plan_report(plan: Plan, mode: str) -> dict[str, object]:
    report: dict[str, object] = {
        "mode": mode,
        "examined": len(plan.rows),
        "planned": len(plan.planned),
        "rejected": len(plan.rows) - len(plan.planned),
        "by_eligibility": dict(sorted(Counter(row.eligibility for row in plan.rows).items())),
        "matched_pairs": list(plan.matched_pairs),
        "problems": list(plan.problems),
        "rows": [_row_dict(row) for row in plan.rows],
    }
    if mode == "dry-run":
        report["model_calls"] = 0
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--live", action="store_true", help="spend: run the planned rows")
    parser.add_argument("--output", type=Path, help="JSONL results path, required with --live")
    parser.add_argument(
        "--real-home",
        action="store_true",
        help="run Codex on the real CODEX_HOME and its own login (ambient instructions load)",
    )
    parser.add_argument(
        "--max-invocations",
        type=int,
        default=None,
        help="hard cap on paid invocations across the run; required with --live",
    )
    parser.add_argument(
        "--arms",
        default=None,
        help="live only: run just these arm letters (for example CD). The config is still "
        "validated whole, because arms C and D need A for the held-constant check",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=1,
        help="passes over the planned rows, repetition outermost (default 1)",
    )
    return parser


def _not_run(row: PlanRow, repetition: int, reason: str) -> dict[str, object]:
    return {
        "status": "NOT_RUN",
        "scenario_id": row.scenario_id,
        "arm": row.arm,
        "harness": row.harness,
        "repetition": repetition,
        "reason": reason,
    }


def _run_live(
    plan: Plan,
    config: BenchmarkConfig,
    scenarios: dict[str, Scenario],
    output: Path,
    *,
    real_home: bool,
    budget: InvocationBudget,
    repetitions: int,
) -> int:
    """Run the planned rows, repetition outermost, and stop at the budget.

    Each row is appended to `output` as it finishes, so an interrupted run keeps
    what it spent. A row the budget cuts off, and every row after it, is written
    as `NOT_RUN` with the reason. Nothing is substituted for a row that did not run.
    """
    failed = False
    spent_out = False
    with output.open("w", encoding="utf-8") as handle:
        for repetition in range(1, repetitions + 1):
            for row in plan.planned:
                if spent_out:
                    item = _not_run(row, repetition, "invocation budget spent")
                else:
                    item, failed_row, spent_out = _run_row(
                        row, config, scenarios, budget, repetition, real_home
                    )
                    failed = failed or failed_row
                handle.write(json.dumps(item) + "\n")
                handle.flush()
    return EXIT_HARNESS_FAILURE if failed else EXIT_OK


def _run_row(
    row: PlanRow,
    config: BenchmarkConfig,
    scenarios: dict[str, Scenario],
    budget: InvocationBudget,
    repetition: int,
    real_home: bool,
) -> tuple[dict[str, object], bool, bool]:
    """Run one row. Returns (result, harness failed, budget spent)."""
    # A fresh backend per row gives each arm its own scratch copy of the scenario,
    # so no arm starts from another arm's edits.
    try:
        with LiveBackend(row.harness, real_home=real_home, budget=budget) as backend:
            result = run_planned(
                row,
                config.strategy_for(row.arm, row.harness),
                scenarios[row.scenario_id],
                backend,
            )
    except BudgetExhaustedError:
        return _not_run(row, repetition, "invocation budget spent mid-row"), False, True
    item = result_to_dict(result)
    item["repetition"] = repetition
    if real_home:
        item["ambient_home"] = {
            "codex_home": "real",
            "confound": "~/.codex AGENTS.md and skills load in every invocation",
        }
    return item, result.status is RunStatus.HARNESS_FAILED, False


def _only_arms(plan: Plan, arms: str) -> Plan:
    """The plan with only the rows of the named arm letters kept, in plan order."""
    wanted = frozenset(arms.upper())
    kept = tuple(row for row in plan.rows if row.arm in wanted)
    return Plan(kept, plan.problems)


def _live_budget(args: argparse.Namespace) -> InvocationBudget | None:
    """The run's invocation budget, `None` when not live. Raises `ValueError` on a bad mix."""
    if not args.live:
        if (
            args.real_home
            or args.max_invocations is not None
            or args.repetitions != 1
            or args.arms is not None
        ):
            raise ValueError("--real-home, --max-invocations, --repetitions and --arms need --live")
        return None
    if args.max_invocations is None or args.max_invocations < 1 or args.repetitions < 1:
        raise ValueError("--live requires --max-invocations >= 1 and --repetitions >= 1")
    return InvocationBudget(args.max_invocations)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.live and args.output is None:
        print("error: --live requires --output", file=sys.stderr)
        return EXIT_CONFIG
    if args.output is not None and not args.live:
        print("error: --output is only valid with --live", file=sys.stderr)
        return EXIT_CONFIG
    try:
        budget = _live_budget(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        config = load_config(args.config)
        records = load_matrix(args.matrix)
        scenarios = load_corpus(args.corpus)
    except (RoutingConfigError, HarnessCapabilityError, RoutingCorpusError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    plan = build_plan(config, records, scenarios)
    if not plan.planned or plan.problems:
        print(json.dumps(plan_report(plan, "dry-run"), indent=2))
        return EXIT_NOTHING_PLANNED
    if not args.live:
        print(json.dumps(plan_report(plan, "dry-run"), indent=2))
        return EXIT_OK
    try:
        require_live_authorization(
            sorted({row.harness for row in plan.planned}), os.environ, real_home=args.real_home
        )
    except LiveGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_AUTH
    if args.arms is not None:
        plan = _only_arms(plan, args.arms)
        if not plan.planned:
            print(f"error: --arms {args.arms} selects no planned row", file=sys.stderr)
            return EXIT_NOTHING_PLANNED
    return _run_live(
        plan,
        config,
        {s.scenario_id: s for s in scenarios},
        args.output,
        real_home=args.real_home,
        budget=budget or InvocationBudget(1),
        repetitions=args.repetitions,
    )


if __name__ == "__main__":
    sys.exit(main())
