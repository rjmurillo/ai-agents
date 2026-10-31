#!/usr/bin/env python3
"""Instrument table for the ai-agents-validation-and-qa skill.

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

SKILL = "ai-agents-validation-and-qa"
SK = ".claude/skills"
_HERE = f"{SK}/{SKILL}/scripts"

_ALLOWLIST_ARGV = [
    "python3",
    "-c",
    "import sys; sys.path.insert(0, '.'); "
    "from scripts.modules.investigation_allowlist import "
    "get_investigation_allowlist_display as g; "
    "r = g(); print(len(r)); print('\\n'.join(r))",
]
_SKIP_CODE = (
    "import ast,sys;t=ast.parse(open(sys.argv[1],encoding='utf-8').read());"
    "d=[n.value for n in ast.walk(t) if isinstance(n,ast.Assign) and "
    "any(getattr(x,'id','')=='_QA_SKIP_CHECKERS' for x in n.targets)];"
    "print('\\n'.join(ast.literal_eval(d[0]).keys()) if d else '')"
)

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "citation-freshness",
        "answers": "Do path:line citations on added lines still point at the cited content?",
        "argv": ["python3", "scripts/validation/check_citation_freshness.py"],
        "source": "Provenance and Maintenance",
    },
    {
        "id": "investigation-allowlist",
        "answers": "Which patterns hold the investigation-only allowlist? Owned by ai-agents-change-control; same argv.",
        "argv": _ALLOWLIST_ARGV,
        "check_path": "scripts/modules/investigation_allowlist.py",
        "source": "Phase 5",
    },
    {
        "id": "qa-skip-evidence",
        "answers": "Which QA skip evidence strings does the session validator accept?",
        "argv": ["python3", "-c", _SKIP_CODE, "scripts/validate_session_json.py"],
        "source": "Phase 5",
    },
    {
        "id": "pester-count",
        "answers": "How many *.Tests.ps1 files exist, and is the Pester warning still live?",
        "argv": ["python3", f"{_HERE}/test_layout.py", "--repo", ".", "pester"],
        "source": "Phase 2",
    },
    {
        "id": "skill-tests",
        "answers": "Which test files does pytest collect by default for a skill? Pass NAME.",
        "argv": ["python3", f"{_HERE}/test_layout.py", "--repo", ".", "skill-tests"],
        "source": "Phase 2 and Phase 6",
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
        "source": "Provenance and Maintenance",
    },
]


def _exists(repo: Path, argv: list[str]) -> bool:
    for tok in argv[1:]:
        if tok.endswith(".py"):
            return (repo / tok).is_file()
    return True


def _row_exists(repo: Path, row: dict[str, Any]) -> bool:
    argv = row["argv"]
    if "check_path" in row:
        return bool((repo / row["check_path"]).is_file())
    if "-c" in argv:
        return all((repo / t).is_file() for t in argv[argv.index("-c") + 2 :])
    return _exists(repo, argv)


def cmd_list(repo: Path) -> int:
    rows = [{**r, "exists": _row_exists(repo, r)} for r in INSTRUMENTS]
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
