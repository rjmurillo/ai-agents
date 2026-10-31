#!/usr/bin/env python3
"""Instrument table for the repository-completion-proof skill.

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

SKILL = "repository-completion-proof"
_PR = ".claude/skills/github/scripts/pr"

INSTRUMENTS: list[dict] = [
    {
        "id": "verify-config",
        "answers": "Are the review config and its command files trusted against the remote anchor (verified: true)?",
        "argv": [
            "uv",
            "run",
            "python",
            f"{_PR}/run_completion_gate.py",
            "--verify-config-only",
            "--json",
        ],
        "source": "Phase 1",
    },
    {
        "id": "merged-state",
        "answers": "Is the PR merged? Read the JSON merged field, not the exit code.",
        "argv": ["uv", "run", "python", f"{_PR}/test_pr_merged.py"],
        "source": "Phase 2",
    },
    {
        "id": "settled-zero",
        "answers": "Do three consecutive complete readings show zero unresolved threads?",
        "argv": ["uv", "run", "python", f"{_PR}/wait_for_unresolved_zero.py"],
        "source": "Phase 2",
    },
    {
        "id": "completion-gate",
        "answers": "Do all configured completion criteria pass (all_passed and per-criterion results)? Dispatches verifiers.",
        "argv": ["uv", "run", "python", f"{_PR}/run_completion_gate.py", "--json"],
        "source": "Phase 2",
    },
    {
        "id": "resolution-shas",
        "answers": "Are the commit SHAs cited in resolved review threads reachable?",
        "argv": ["uv", "run", "python", f"{_PR}/check_review_thread_resolution_shas.py"],
        "source": "Phase 2",
    },
    {
        "id": "suppressed-findings",
        "answers": "Are suppressed review findings dispositioned?",
        "argv": ["uv", "run", "python", f"{_PR}/check_suppressed_review_findings.py"],
        "source": "Phase 2",
    },
    {
        "id": "merge-ready",
        "answers": "Is the PR merge-ready on the live state GitHub reports?",
        "argv": ["uv", "run", "python", f"{_PR}/test_pr_merge_ready.py"],
        "source": "Phase 3",
    },
    {
        "id": "live-state",
        "answers": "What is the PR's current live state (head, checks, threads)?",
        "argv": ["uv", "run", "python", f"{_PR}/check_pr_live_state.py"],
        "source": "Phase 3",
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


def _rows(repo: Path) -> list[dict]:
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
