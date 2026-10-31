#!/usr/bin/env python3
"""Instrument table for the repository-pr-recovery skill.

  instruments.py --repo . list
  instruments.py --repo . run <id> [-- args...]

Exit codes: 0 ok, 1 a listed instrument file is missing, 2 bad arguments or
unknown id, 3 the run target failed to start. A started child's exit code
passes through unchanged.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL = "repository-pr-recovery"
_GH = ".claude/skills/github/scripts/pr"
_HERE = ".claude/skills/repository-pr-recovery/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "why-pr-blocked",
        "answers": "Which diagnosed causes block this PR (checks, threads, conflicts)?",
        "argv": ["python3", f"{_GH}/why_pr_blocked.py"],
        "source": "Phase 1",
    },
    {
        "id": "triage-red-check",
        "answers": "Is this red check inherited from the base branch (GREEN_ON_MAIN, RED_ON_MAIN, PR_ONLY, CANCELLED_ON_MAIN, UNKNOWN)?",
        "argv": ["python3", f"{_GH}/triage_red_check.py"],
        "source": "Phase 1",
    },
    {
        "id": "check-logs",
        "answers": "What do the logs of a failed check say?",
        "argv": ["python3", f"{_GH}/get_pr_check_logs.py"],
        "source": "Phase 1",
    },
    {
        "id": "review-threads",
        "answers": "Which review threads exist and which are unresolved?",
        "argv": ["python3", f"{_GH}/get_pr_review_threads.py"],
        "source": "Phase 1",
    },
    {
        "id": "required-context-conditions",
        "answers": "Do workflows that produce a pinned required context hide step conditions that skip the verification?",
        "argv": ["uv", "run", "python", "scripts/validation/check_required_context_conditions.py"],
        "source": "Phase 2",
    },
    {
        "id": "producer-join",
        "answers": "Is each required context produced by its required app on the evaluated SHA?",
        "argv": ["python3", f"{_HERE}/required_check_producer_join.py", "--repo", "."],
        "source": "Phase 2",
    },
    {
        "id": "drift-self-check",
        "answers": "Does this skill's reverify.json still hold at HEAD?",
        "argv": [
            "python3",
            ".claude/skills/skill-bootstrap/scripts/bootstrap_drift.py",
            "check",
            "--repo",
            ".",
            "--skills-root",
            ".claude/skills",
            "--name",
            SKILL,
            "--require",
        ],
        "source": "Provenance and Maintenance",
    },
]


def _target(argv: list[str]) -> str | None:
    """Return the repo-relative file an instrument executes, if any."""
    if argv[0] == "python3":
        return argv[1]
    if argv[:3] == ["uv", "run", "python"]:
        return argv[3]
    return None


def _rows(repo: Path) -> list[dict[str, Any]]:
    rows = []
    for row in INSTRUMENTS:
        target = _target(row["argv"])
        rows.append({**row, "exists": target is None or (repo / target).is_file()})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    run_p = sub.add_parser("run")
    run_p.add_argument("id")
    run_p.add_argument("extra", nargs=argparse.REMAINDER)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code in (0, None) else 2
    repo = Path(args.repo)
    rows = _rows(repo)
    if args.cmd == "list":
        missing = [r["id"] for r in rows if not r["exists"]]
        print(
            json.dumps(
                {"skill": SKILL, "instruments": rows, "examined": len(rows), "missing": missing},
                indent=2,
            )
        )
        return 1 if missing else 0
    row = next((r for r in rows if r["id"] == args.id), None)
    if row is None:
        print(
            json.dumps({"error": f"unknown instrument id: {args.id}", "examined": len(rows)}),
            file=sys.stderr,
        )
        return 2
    extra = [a for a in args.extra if a != "--"]
    try:
        return subprocess.run(row["argv"] + extra, cwd=repo, check=False).returncode
    except OSError as exc:
        print(
            json.dumps({"error": f"cannot start {row['argv'][0]}: {exc}", "examined": len(rows)}),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
