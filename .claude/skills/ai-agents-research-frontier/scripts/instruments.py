#!/usr/bin/env python3
"""Instrument table for ai-agents-research-frontier.

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

SKILL = "ai-agents-research-frontier"
SK = ".claude/skills"

COUNTS_CODE = (
    "import glob,json;"
    "print(json.dumps({"
    "'skills':len(glob.glob('.claude/skills/*/SKILL.md')),"
    "'rules':len(glob.glob('.claude/rules/*.md')),"
    "'rule_scenarios':len(glob.glob('tests/evals/rule-scenarios/*')),"
    "'retros':len([f for f in glob.glob('.project-toolkit/retrospective/*.md')"
    " if not f.endswith('INDEX.md')]),"
    "'memories_recursive_md':len(glob.glob('.serena/memories/**/*.md',recursive=True))}))"
)

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "corpus-counts",
        "answers": "How many skills, rules, rule scenario fixtures, retros, and memories exist now?",
        "argv": ["python3", "-c", COUNTS_CODE],
        "source": "SKILL.md Phase 1",
    },
    {
        "id": "corpus-index",
        "answers": "How many retros exist, how many INDEX.md covers, how many failure modes and memories?",
        "argv": [
            "python3",
            ".claude/skills/ai-agents-failure-archaeology/scripts/corpus_index.py",
            "--repo",
            ".",
        ],
        "source": "SKILL.md Phase 1",
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
        sys.stdout.flush()
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
