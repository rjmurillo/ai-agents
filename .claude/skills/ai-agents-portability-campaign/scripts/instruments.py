#!/usr/bin/env python3
"""Instrument dispatcher for the ai-agents-portability-campaign skill.

  instruments.py --repo . list
  instruments.py --repo . run <id> [-- args...]

`list` prints every linked instrument and whether its files exist (exit 1 when any
is missing). `run` executes the instrument argv from the repo root and passes the
child's exit code and output through unchanged, so a `grep` row prints text while a
script row prints its own JSON; only `list` promises JSON with `examined`. Exit codes:
0 ok, 1 missing instrument file, 2 bad arguments or unknown id, 3 the run target
failed to start.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL = "ai-agents-portability-campaign"
SCRIPTS = f".claude/skills/{SKILL}/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "hook-counts",
        "answers": "How many hook events and registrations does each hook manifest hold?",
        "argv": ["python3", f"{SCRIPTS}/hook_inventory.py", "--repo", ".", "counts"],
        "source": "Phase 4 Inventories",
    },
    {
        "id": "phase-tests",
        "answers": "Does every pytest path the skill names exist?",
        "argv": ["python3", f"{SCRIPTS}/hook_inventory.py", "--repo", ".", "phase-tests"],
        "source": "Phase 3 and Phase 5",
    },
    {
        "id": "qualifiers",
        "answers": "Does every shipped reference to this skill carry the ai-agents repository qualifier?",
        "argv": ["python3", f"{SCRIPTS}/hook_inventory.py", "--repo", ".", "qualifiers"],
        "source": "Authority boundary",
    },
    {
        "id": "event-map",
        "answers": "Which Claude event maps to which Copilot event (eventRemap)?",
        "argv": ["grep", "-n", "-A12", "eventRemap:", "templates/platforms/copilot-cli.yaml"],
        "source": "Phase 1 event mapping",
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
