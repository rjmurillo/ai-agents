#!/usr/bin/env python3
"""CLI and rendering for the eval-run rollup (issue #2787).

Standalone consumer of the eval harness JSONL event log. The data model and
aggregation live in `_run_rollup_core`; this module renders a `RollupResult` as
a table or JSON and exposes the command-line entry point. The core names are
re-exported so callers and tests can import everything from `eval_run_rollup`.

See `_run_rollup_core` for the design note on why this reuses the existing log
path rather than bumping the `RunRecord` schema.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# The eval helper modules import each other by bare name (`from _eval_common
# import ...`), so `scripts/eval` must be importable as a flat directory.
_EVAL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_DIR.parents[1]
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from _run_rollup_core import (  # noqa: E402  (path bootstrap must run first)
    DEFAULT_GLOB,
    DEFAULT_SIGMA,
    AgentRollup,
    DriftFlag,
    RollupResult,
    RunTally,
    _build_agent_rollups,
    _coerce_record,
    _CoercedRecord,
    _drift_flags,
    agent_from_path,
    cost_usd,
    iter_tallies,
    rollup,
    run_id_from_path,
)

__all__ = [
    "DEFAULT_GLOB",
    "DEFAULT_SIGMA",
    "AgentRollup",
    "DriftFlag",
    "RollupResult",
    "RunTally",
    "_CoercedRecord",
    "_build_agent_rollups",
    "_coerce_record",
    "_drift_flags",
    "agent_from_path",
    "cost_usd",
    "iter_tallies",
    "rollup",
    "run_id_from_path",
    "to_human",
    "to_json",
    "main",
    "EXIT_OK",
    "EXIT_CONFIG",
]

# Exit codes follow the AGENTS.md contract.
EXIT_OK = 0
EXIT_CONFIG = 2


def _resolve_repo_dir(path: Path, *, arg_name: str) -> Path:
    """Resolve a CLI directory under the repository root, rejecting traversal."""
    candidate = path if path.is_absolute() else _REPO_ROOT / path
    try:
        resolved = candidate.expanduser().resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"{arg_name} {path} is not a valid path: {exc}") from exc
    repo_root = _REPO_ROOT.resolve()
    if not resolved.is_relative_to(repo_root):
        raise ValueError(f"{arg_name} {path} is outside repository root")
    if not resolved.is_dir():
        raise ValueError(f"{arg_name} {path} is not a directory")
    return resolved


def to_json(result: RollupResult) -> dict[str, object]:
    """Machine-readable rollup. Stable shape for downstream tooling."""
    return {
        "sigma": result.sigma,
        "pricing_rate_as_of": result.pricing_rate_as_of,
        "files_scanned": result.files_scanned,
        "files_skipped": result.files_skipped,
        "runs_counted": result.runs_counted,
        "lines_skipped": result.lines_skipped,
        "unpriced_runs": result.unpriced_runs,
        "total_cost_usd": round(result.total_cost, 6),
        "total_tokens": result.total_tokens,
        "agents": [
            {
                "agent": a.agent,
                "runs": a.runs,
                "errors": a.errors,
                "tokens_in": a.tokens_in,
                "tokens_out": a.tokens_out,
                "tokens": a.tokens,
                "cost_usd": round(a.cost, 6),
                "cost_priced_runs": a.cost_priced_runs,
                "mean_latency_ms": round(a.mean_latency_ms, 2),
                "stdev_latency_ms": round(a.stdev_latency_ms, 2),
                "mean_cost_usd": round(a.mean_cost, 6),
                "stdev_cost_usd": round(a.stdev_cost, 6),
            }
            for a in result.agents
        ],
        "drift": [
            {
                "agent": d.agent,
                "fixture_id": d.fixture_id,
                "variant": d.variant,
                "run_id": d.run_id,
                "metric": d.metric,
                "value": round(d.value, 6),
                "threshold": round(d.threshold, 6),
            }
            for d in result.drift
        ],
    }


def to_human(result: RollupResult) -> str:
    """Operator-facing rollup table plus drift flags."""
    lines: list[str] = []
    lines.append(
        f"Eval run rollup: {result.runs_counted} run(s) across "
        f"{result.files_scanned} log file(s), sigma={result.sigma:g}, "
        f"pricing as of {result.pricing_rate_as_of}"
    )
    if result.files_skipped or result.lines_skipped or result.unpriced_runs:
        lines.append(
            f"  skipped {result.files_skipped} unreadable file(s), "
            f"{result.lines_skipped} malformed line(s); "
            f"{result.unpriced_runs} run(s) had no pricing rate"
        )
    if not result.agents:
        lines.append("  no runs found")
        return "\n".join(lines)

    header = (
        f"{'agent':<22} {'runs':>5} {'errs':>5} {'tokens':>10} "
        f"{'cost_usd':>10} {'mean_lat_ms':>12}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for a in result.agents:
        lines.append(
            f"{a.agent:<22} {a.runs:>5} {a.errors:>5} {a.tokens:>10} "
            f"{a.cost:>10.4f} {a.mean_latency_ms:>12.1f}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"{'TOTAL':<22} {result.runs_counted:>5} "
        f"{sum(a.errors for a in result.agents):>5} "
        f"{result.total_tokens:>10} {result.total_cost:>10.4f} {'':>12}"
    )

    if result.drift:
        lines.append("")
        lines.append(
            f"Drift flags ({len(result.drift)}), runs beyond "
            f"mean + {result.sigma:g}*sigma:"
        )
        for d in result.drift:
            unit = "ms" if d.metric == "latency_ms" else "usd"
            lines.append(
                f"  {d.agent}/{d.variant}/{d.fixture_id} [{d.run_id}]: "
                f"{d.metric}={d.value:.4f}{unit} > {d.threshold:.4f}{unit}"
            )
    else:
        lines.append("")
        lines.append("Drift flags: none")
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Roll up per-run cost/latency/token tallies from the eval harness "
            "JSONL logs and flag drift beyond N sigma (issue #2787)."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("evals"),
        help="Directory holding <agent>-spike/runs/<RUN_ID>/runs.jsonl (default: evals).",
    )
    parser.add_argument(
        "--glob",
        default=DEFAULT_GLOB,
        help=f"Glob under --root for run logs (default: {DEFAULT_GLOB}).",
    )
    parser.add_argument(
        "--sigma",
        type=float,
        default=DEFAULT_SIGMA,
        help=f"Drift threshold in standard deviations (default: {DEFAULT_SIGMA}).",
    )
    parser.add_argument(
        "--agent",
        default=None,
        help="Keep only runs whose derived agent name matches exactly.",
    )
    parser.add_argument(
        "--output-format",
        choices=("human", "json"),
        default="human",
        help="Render the rollup as a table (human) or JSON (default: human).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        root = _resolve_repo_dir(args.root, arg_name="--root")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    if args.sigma < 0 or math.isnan(args.sigma):
        print(
            f"error: --sigma must be a non-negative number, got {args.sigma}",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    result = rollup(
        root, glob=args.glob, sigma=args.sigma, agent_filter=args.agent
    )
    if args.output_format == "json":
        print(json.dumps(to_json(result), indent=2, sort_keys=True))
    else:
        print(to_human(result))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
