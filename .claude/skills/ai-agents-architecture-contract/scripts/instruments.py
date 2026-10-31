#!/usr/bin/env python3
"""Instrument dispatcher for the ai-agents-architecture-contract skill.

  instruments.py --repo . list
  instruments.py --repo . run <id> [-- args...]

`list` prints every linked instrument and whether its files exist (exit 1 when any
is missing). `run` executes the instrument argv from the repo root and passes the
child's exit code through. Exit codes: 0 ok, 1 missing instrument file, 2 bad
arguments or unknown id, 3 the run target failed to start.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL = "ai-agents-architecture-contract"
SCRIPTS = f".claude/skills/{SKILL}/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "adr-status",
        "answers": "What are the status, superseded-by, and implemented flag of each cited ADR?",
        "argv": ["python3", f"{SCRIPTS}/contract_probe.py", "--repo", ".", "adrs"],
        "source": "Phase 2 and references/adr-decisions.md",
    },
    {
        "id": "guard-lines",
        "answers": "Where are assert_no_claude_writes and its call sites?",
        "argv": ["python3", f"{SCRIPTS}/contract_probe.py", "--repo", ".", "guard"],
        "source": "Phase 1 direction rule",
    },
    {
        "id": "hook-counts",
        "answers": "How many hook events and registrations does each hook manifest hold?",
        "argv": [
            "python3",
            ".claude/skills/ai-agents-portability-campaign/scripts/hook_inventory.py",
            "--repo",
            ".",
            "counts",
        ],
        "source": "Phase 3 registration split",
    },
    {
        "id": "generator-path",
        "answers": "Which tree is canonical for a repo path, and what regenerates it? Pass the path after --.",
        "argv": [
            "python3",
            ".claude/skills/ai-agents-generation-and-release/scripts/generator_inventory.py",
            "--repo",
            ".",
            "path",
        ],
        "source": "Phase 1 source-of-truth table",
    },
    {
        "id": "version-gate",
        "answers": "Does any plugin manifest or marketplace entry carry a version field?",
        "argv": ["python3", "build/scripts/validate_plugin_version_bump.py"],
        "source": "Phase 5 plugin surfaces",
    },
    {
        "id": "claims",
        "answers": "Which paths and test node ids cited by this skill no longer exist?",
        "argv": [
            "python3",
            ".claude/skills/skill-bootstrap/scripts/bootstrap_mine.py",
            "claims",
            "--repo",
            ".",
            ".claude/skills/ai-agents-architecture-contract",
        ],
        "source": "references/provenance.md",
    },
    {
        "id": "drift-self-check",
        "answers": "Has this skill drifted from its reverify.json checks?",
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


def _repo_paths(argv: list[str]) -> list[str]:
    """Return argv tokens that look like repo-relative file paths."""
    return [a for a in argv[1:] if "/" in a and not a.startswith("-")]


def row_exists(repo: Path, row: dict[str, Any]) -> bool:
    return all((repo / p).exists() for p in _repo_paths(row["argv"]))


def cmd_list(repo: Path) -> int:
    rows = []
    missing = []
    for row in INSTRUMENTS:
        exists = row_exists(repo, row)
        rows.append({**row, "exists": exists})
        if not exists:
            missing.append(row["id"])
    print(
        json.dumps(
            {"skill": SKILL, "instruments": rows, "examined": len(rows), "missing": missing},
            indent=2,
        )
    )
    return 1 if missing else 0


def cmd_run(repo: Path, instrument_id: str, extra: list[str]) -> int:
    row = next((r for r in INSTRUMENTS if r["id"] == instrument_id), None)
    if row is None:
        known = ", ".join(r["id"] for r in INSTRUMENTS)
        print(f"error: unknown instrument '{instrument_id}' (known: {known})", file=sys.stderr)
        return 2
    try:
        sys.stdout.flush()
        return subprocess.run([*row["argv"], *extra], cwd=repo, check=False).returncode
    except OSError as exc:
        print(f"error: cannot start {row['argv'][0]}: {exc}", file=sys.stderr)
        return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="repository root (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list instruments and whether each exists")
    run = sub.add_parser("run", help="run one instrument")
    run.add_argument("id")
    run.add_argument("extra", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"error: --repo {args.repo} is not a directory", file=sys.stderr)
        return 2
    if args.command == "list":
        return cmd_list(repo)
    extra = args.extra[1:] if args.extra[:1] == ["--"] else args.extra
    return cmd_run(repo, args.id, extra)


if __name__ == "__main__":
    sys.exit(main())
