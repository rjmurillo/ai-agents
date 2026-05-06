#!/usr/bin/env python3
"""Run the guard maturity report end-to-end.

Thin wrapper around the two build/scripts:

1. ``aggregate_guard_intercepts.py``
2. ``classify_guard_maturity.py``

Output is a human-readable table printed to stdout, plus the raw JSON
report on stderr (so a caller can capture it with ``2>``).

The wrapper keeps logic out of the SKILL.md prose (the skill should
describe what to do; the script should do it). All tier and fitness
math lives in the classifier; this file is presentation only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
AGGREGATE = REPO_ROOT / "build" / "scripts" / "aggregate_guard_intercepts.py"
CLASSIFY = REPO_ROOT / "build" / "scripts" / "classify_guard_maturity.py"

# Severity sort: Harmful first (act now), then Inert (prune), then the
# happy tiers. Within a tier, sort by intercepts descending so the
# loudest guards float to the top.
TIER_ORDER = {
    "Harmful": 0,
    "Inert": 1,
    "Budding": 2,
    "Growing": 3,
    "Mature": 4,
    "Proficient": 5,
}


def _run_aggregate(known_guards: list[str], source: str | None) -> dict:
    cmd = [sys.executable, str(AGGREGATE)]
    for g in known_guards:
        cmd.extend(["--guard", g])
    if source:
        cmd.extend(["--source", source])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return json.loads(proc.stdout)


def _run_classify(summary: dict, treat_unseen_as_inert: bool) -> dict:
    cmd = [sys.executable, str(CLASSIFY)]
    if treat_unseen_as_inert:
        cmd.append("--treat-unseen-as-inert")
    proc = subprocess.run(
        cmd,
        input=json.dumps(summary),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)
    return json.loads(proc.stdout)


def _format_table(report: dict) -> str:
    rows = sorted(
        report.values(),
        key=lambda r: (TIER_ORDER.get(r["tier"], 99), -r["intercepts"], r["guard"]),
    )
    if not rows:
        return "(no guards in report)\n"
    header = f"{'tier':<11} {'guard':<22} {'intercepts':>10} {'fitness':>8} {'age_days':>9}"
    lines = [header, "-" * len(header)]
    for r in rows:
        age = r.get("days_since_first_event")
        age_s = f"{age:.1f}" if isinstance(age, (int, float)) else "n/a"
        lines.append(
            f"{r['tier']:<11} {r['guard']:<22} {r['intercepts']:>10} "
            f"{r['fitness']:>+7.2f} {age_s:>9}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the guard maturity report (aggregate + classify).",
    )
    parser.add_argument(
        "--guard",
        action="append",
        default=[
            "markdown-lint",
            "manifest-count",
            "pr-description",
            "session-log",
        ],
        help=("Guard name to include even with zero events. Repeatable. "
              "Defaults cover M2-M5."),
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Override telemetry source path (file or directory).",
    )
    parser.add_argument(
        "--treat-unseen-as-inert",
        action="store_true",
        help="Mark guards with no events as Inert instead of Budding.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of the human-readable table.",
    )
    args = parser.parse_args(argv)

    summary = _run_aggregate(args.guard, args.source)
    report = _run_classify(summary, args.treat_unseen_as_inert)

    if args.json:
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(_format_table(report))
        # Stash the raw JSON on stderr so callers can capture both.
        json.dump(report, sys.stderr, indent=2, sort_keys=True)
        sys.stderr.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
