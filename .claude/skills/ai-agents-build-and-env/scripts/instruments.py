#!/usr/bin/env python3
"""Instrument table for the ai-agents-build-and-env skill.

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

SKILL = "ai-agents-build-and-env"
_HERE = ".claude/skills/ai-agents-build-and-env/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "env-pins",
        "answers": "What are the interpreter, lefthook, PyYAML, requires-python, Node major, and syntax floor pins right now?",
        "argv": ["python3", f"{_HERE}/env_probe.py", "--repo", ".", "pins"],
        "source": "Phase 1 and Known Traps",
    },
    {
        "id": "env-file",
        "answers": "Does .env exist, stay untracked, and which keys does .env.example list?",
        "argv": ["python3", f"{_HERE}/env_probe.py", "--repo", ".", "envfile"],
        "source": "Phase 4 and Verification",
    },
    {
        "id": "env-smoke",
        "answers": "Do lefthook version, check-install, and the tests/test_paths.py collection pass?",
        "argv": ["python3", f"{_HERE}/env_probe.py", "--repo", ".", "smoke"],
        "source": "Phase 3 and Verification",
    },
    {
        "id": "venv-stale-check",
        "answers": "Is a moved worktree's .venv launcher shebang stale?",
        "argv": ["uv", "run", "python", "scripts/maintenance/repair_worktree_venv.py", "--check"],
        "source": "Known Traps",
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
