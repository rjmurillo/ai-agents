#!/usr/bin/env python3
"""Instrument table for ai-agents-change-control.

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

SKILL = "ai-agents-change-control"
SK = ".claude/skills"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "classify-change",
        "answers": "Which change class and which gates does each changed path trigger?",
        "argv": ["python3", f"{SK}/{SKILL}/scripts/classify_change.py", "--repo", ".", "--staged"],
        "source": "SKILL.md Phase 1 and Phase 2",
    },
    {
        "id": "investigation-allowlist",
        "answers": "Which patterns does the enforced investigation-only allowlist hold, and how many?",
        "argv": [
            "python3",
            "-c",
            "import sys; sys.path.insert(0, '.'); "
            "from scripts.modules.investigation_allowlist import "
            "get_investigation_allowlist_display as g; "
            "r = g(); print(len(r)); print('\\n'.join(r))",
        ],
        "check_path": "scripts/modules/investigation_allowlist.py",
        "source": "SKILL.md Phase 1",
    },
    {
        "id": "drift-agents",
        "answers": "Do generated agent files match their templates?",
        "argv": ["uv", "run", "python", "build/generate_agents.py", "--validate"],
        "check_path": "build/generate_agents.py",
        "source": "SKILL.md Phase 2",
    },
    {
        "id": "drift-build-all",
        "answers": "Do all generated trees match their canonical sources?",
        "argv": ["uv", "run", "python", "build/scripts/build_all.py", "--check"],
        "check_path": "build/scripts/build_all.py",
        "source": "SKILL.md Phase 2",
    },
    {
        "id": "plugin-version-absent",
        "answers": "Does any plugin manifest or marketplace entry carry a version field?",
        "argv": ["python3", "build/scripts/validate_plugin_version_bump.py"],
        "source": "SKILL.md Verification",
    },
    {
        "id": "dash-check",
        "answers": "Do changed .md and .py files on this branch contain em or en dashes?",
        "argv": [
            "uv",
            "run",
            "python",
            "-c",
            "import sys; sys.path.insert(0, 'scripts/validation'); "
            "from pathlib import Path; "
            "from checks_dash import validate_dash_prohibition as v; "
            "o = v(Path('.')); print(o); sys.exit(0 if o.state.name == 'PASS' else 1)",
        ],
        "check_path": "scripts/validation/checks_dash.py",
        "source": "SKILL.md Verification",
    },
    {
        "id": "citation-freshness",
        "answers": "Do path:line citations on added lines still hold at HEAD?",
        "argv": ["python3", "scripts/validation/check_citation_freshness.py"],
        "source": "SKILL.md Verification",
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


def _exists(repo: Path, row: dict[str, Any]) -> bool:
    if "check_path" in row:
        return bool((repo / row["check_path"]).is_file())
    for tok in row["argv"][1:]:
        if tok.endswith(".py"):
            return bool((repo / tok).is_file())
    return True


def cmd_list(repo: Path) -> int:
    rows = [{**r, "exists": _exists(repo, r)} for r in INSTRUMENTS]
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
