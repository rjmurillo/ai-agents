#!/usr/bin/env python3
"""Instrument table for the repository-consumer-proof skill.

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

SKILL = "repository-consumer-proof"
_HERE = ".claude/skills/repository-consumer-proof/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "generated-output-check",
        "answers": "Does generated output match templates and committed state?",
        "argv": ["uv", "run", "python", "build/scripts/build_all.py", "--check"],
        "source": "Phase 2 generation step",
    },
    {
        "id": "installed-dispatcher",
        "answers": "Did the installed completion dispatcher run its bundled criteria end to end?",
        "argv": ["uv", "run", "pytest", "tests/test_run_completion_gate_install.py", "-q"],
        "source": "Phase 2 installed dispatcher",
    },
    {
        "id": "hook-runtime-contract",
        "answers": "Do hooks run from a foreign cwd and do plugin-root variables resolve?",
        "argv": [
            "uv",
            "run",
            "pytest",
            "tests/build_scripts/test_generate_hooks_runtime_contract.py",
            "tests/build_scripts/test_generate_hooks_plugin_root.py",
            "-q",
        ],
        "source": "Phase 2 hook suites",
    },
    {
        "id": "runtime-parity-dry-run",
        "answers": "Do the completion-terminal parity fixtures pass their deterministic controls? Caller passes `-- --model <id>`.",
        "argv": [
            "uv",
            "run",
            "python",
            "scripts/eval/eval_runtime_parity.py",
            "--fixtures",
            "tests/evals/completion-terminal-runtime-fixtures.json",
            "--harnesses",
            "claude",
            "--dry-run",
        ],
        "source": "Phase 3 dry-run",
    },
    {
        "id": "artifact-owner",
        "answers": "Which layer and binplace row own a given repo path?",
        "argv": ["python3", f"{_HERE}/artifact_owner.py", "--repo", "."],
        "source": "Phase 1 generated artifacts",
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
    if argv[:3] == ["uv", "run", "pytest"]:
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
