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
import os
import subprocess
import sys
from pathlib import Path


def _resolve_repo_root() -> Path:
    """Locate the repo root robustly across install shapes.

    The same source file lives at two different depths:
    - canonical: ``.claude/skills/guard-maturity/scripts/run_report.py`` →
      ``parents[4]`` is the repo root.
    - copilot-cli mirror: ``src/copilot-cli/skills/guard-maturity/scripts/
      run_report.py`` → ``parents[4]`` is ``<repo>/src``, NOT the repo
      root. A naive ``parents[4]`` makes ``AGGREGATE`` / ``CLASSIFY`` point
      at ``<repo>/src/build/scripts/...`` which does not exist.

    Resolution order:
    1. ``CLAUDE_PLUGIN_ROOT`` env var (vendor install / harness).
    2. ``GITHUB_WORKSPACE`` env var (CI).
    3. Walk up from ``__file__`` looking for ``AGENTS.md`` (in-repo
       canonical) or ``.git`` (any local clone).
    4. Fall back to ``parents[4]`` (preserves prior behavior for the
       canonical layout when none of the above is present).
    """
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root and Path(plugin_root).is_dir():
        return Path(plugin_root)
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace and Path(workspace).is_dir():
        return Path(workspace)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "AGENTS.md").is_file() or (parent / ".git").is_dir():
            return parent
    return here.parents[4]


REPO_ROOT = _resolve_repo_root()
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


def _parse_subprocess_json(stdout: str, child_label: str) -> dict:
    """Parse JSON from a child subprocess's stdout with a controlled error.

    A successful (returncode 0) child whose stdout is empty or non-JSON is
    a contract violation. Raise SystemExit(3) (external error per ADR-035)
    rather than letting json.JSONDecodeError dump a traceback.
    """
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(
            f"error: {child_label} returned non-JSON stdout "
            f"({len(stdout)} bytes): {exc}\n"
        )
        raise SystemExit(3) from exc


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
    return _parse_subprocess_json(proc.stdout, "aggregate_guard_intercepts.py")


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
    return _parse_subprocess_json(proc.stdout, "classify_guard_maturity.py")


def _format_table(report: dict) -> str:
    rows = sorted(
        report.values(),
        key=lambda r: (TIER_ORDER.get(r["tier"], 99), -r["intercepts"], r["guard"]),
    )
    if not rows:
        return "(no guards in report)\n"
    header = f"{'tier':<11} {'guard':<22} {'intercepts':>10} {'fitness':>7} {'age_days':>9}"
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
        default=None,
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

    if args.guard is None:
        args.guard = [
            "markdown-lint",
            "manifest-count",
            "pr-description",
            "session-log",
        ]

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
