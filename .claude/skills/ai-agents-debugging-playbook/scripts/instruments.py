#!/usr/bin/env python3
"""Instrument table for ai-agents-debugging-playbook.

`list` prints every instrument row with exists true/false (exit 1 if any is missing).
`run <id> [-- args]` execs the instrument from the repo root and passes its exit code through.
Exit codes: 0 ok, 1 missing instrument, 2 bad arguments or unknown id, 3 run target failed to start.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL = "ai-agents-debugging-playbook"
SK = ".claude/skills"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "first-command-stash",
        "answers": "Which git stash entries are foreign (WIP branch not checked out in any worktree)?",
        "argv": ["python3", f"{SK}/{SKILL}/scripts/first_command.py", "--repo", ".", "stash"],
        "source": "SKILL.md Shared checkout",
    },
    {
        "id": "first-command-lag",
        "answers": "How far does HEAD lag origin/main (left and right commit counts)?",
        "argv": ["python3", f"{SK}/{SKILL}/scripts/first_command.py", "--repo", ".", "lag"],
        "source": "SKILL.md Shared checkout",
    },
    {
        "id": "plugin-version-bump",
        "answers": "Does any plugin manifest or marketplace entry carry a version field?",
        "argv": ["python3", "build/scripts/validate_plugin_version_bump.py"],
        "source": "SKILL.md CI reds",
    },
    {
        "id": "dash-scan",
        "answers": "Do changed files carry an em or en dash?",
        "argv": ["uv", "run", "python", "scripts/validation/checks_dash.py"],
        "source": "SKILL.md Local blocks",
    },
    {
        "id": "spec-id-uniqueness",
        "answers": "Are REQ and TASK spec ids unique in the working tree?",
        "argv": ["python3", "scripts/validation/check_spec_id_uniqueness.py"],
        "source": "SKILL.md Shared checkout",
    },
    {
        "id": "python-syntax",
        "answers": "Does every tracked Python file parse at the 3.10 floor?",
        "argv": ["python3", "scripts/validation/validate_python_syntax.py"],
        "source": "SKILL.md CI reds",
    },
    {
        "id": "drift-ci",
        "answers": "Do the generated agent trees drift from their sources (CI drift step)?",
        "argv": ["uv", "run", "python", "build/scripts/run_drift_check_ci.py"],
        "source": "SKILL.md CI reds",
    },
    {
        "id": "drift-self-check",
        "answers": "Has this skill drifted from its reverify.json checks?",
        "argv": [
            "python3",
            f"{SK}/skill-bootstrap/scripts/bootstrap_drift.py",
            "check",
            "--repo",
            ".",
            "--skills-root",
            SK,
            "--name",
            SKILL,
            "--require",
        ],
        "source": "SKILL.md Provenance and Maintenance",
    },
]


def _exists(repo: Path, argv: list[str]) -> bool:
    for tok in argv[1:]:
        if tok.endswith(".py"):
            return (repo / tok).is_file()
    return True


def cmd_list(repo: Path) -> int:
    rows = [{**r, "exists": _exists(repo, r["argv"])} for r in INSTRUMENTS]
    missing = [r["id"] for r in rows if not r["exists"]]
    print(
        json.dumps(
            {"skill": SKILL, "instruments": rows, "examined": len(rows), "missing": missing},
            indent=2,
        )
    )
    return 1 if missing else 0


def cmd_run(repo: Path, ident: str, extra: list[str]) -> int:
    row = next((r for r in INSTRUMENTS if r["id"] == ident), None)
    if row is None:
        print(json.dumps({"error": f"unknown instrument id: {ident}"}), file=sys.stderr)
        return 2
    try:
        return subprocess.run(row["argv"] + extra, cwd=repo, check=False).returncode
    except OSError as exc:
        print(json.dumps({"error": f"failed to start: {exc}"}), file=sys.stderr)
        return 3


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="List or run this skill's instruments.")
    p.add_argument("--repo", default=".", help="repository root (default: .)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="print every instrument row")
    r = sub.add_parser("run", help="run one instrument")
    r.add_argument("id")
    r.add_argument("args", nargs=argparse.REMAINDER)
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    if a.cmd == "list":
        return cmd_list(repo)
    extra = a.args[1:] if a.args[:1] == ["--"] else a.args
    return cmd_run(repo, a.id, extra)


if __name__ == "__main__":
    sys.exit(main())
