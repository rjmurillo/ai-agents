#!/usr/bin/env python3
"""Instrument table for the ai-agents-config-catalog skill.

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

SKILL = "ai-agents-config-catalog"
_HERE = ".claude/skills/ai-agents-config-catalog/scripts"

INSTRUMENTS: list[dict] = [
    {
        "id": "flag-locate",
        "answers": "Which file:line defines this flag, marker, or env var? Pass an id after --, or --list.",
        "argv": ["python3", f"{_HERE}/flag_locator.py", "--repo", ".", "locate"],
        "source": "Process step 4 and Provenance and Maintenance",
    },
    {
        "id": "pytest-markers",
        "answers": "Which pytest markers does pyproject.toml declare?",
        "argv": ["python3", f"{_HERE}/flag_locator.py", "--repo", ".", "markers"],
        "source": "Environment Variables: Tests and Tooling",
    },
    {
        "id": "retired-flags",
        "answers": "Are the retired flags absent from CONTRIBUTING.md and pre_pr.py?",
        "argv": ["python3", f"{_HERE}/flag_locator.py", "--repo", ".", "retired"],
        "source": "Removed and Stale Flags",
    },
    {
        "id": "hook-counts",
        "answers": "How many events and registrations does each hook surface hold?",
        "argv": [
            "python3",
            ".claude/skills/ai-agents-portability-campaign/scripts/hook_inventory.py",
            "--repo",
            ".",
            "counts",
        ],
        "source": "Hook Registration Surfaces",
    },
    {
        "id": "manifest-version",
        "answers": "Does any plugin manifest or marketplace entry carry a version field?",
        "argv": ["uv", "run", "python", "build/scripts/validate_plugin_version_bump.py"],
        "source": "Plugin Manifest Version Prohibition",
    },
    {
        "id": "lefthook-validate",
        "answers": "Are the Git hook jobs, filters, and validators in lefthook.yml valid?",
        "argv": ["uv", "run", "--frozen", "lefthook", "validate"],
        "source": "Git Hook Configuration",
    },
    {
        "id": "qa-investigation-eligible",
        "answers": "Do the staged files qualify for SKIPPED: investigation-only?",
        "argv": ["uv", "run", "python", "scripts/validation/test_investigation_eligibility.py"],
        "source": "QA Skip Verdicts",
    },
    {
        "id": "qa-docs-only-eligible",
        "answers": "Do the staged files qualify for SKIPPED: docs-only?",
        "argv": ["uv", "run", "python", "scripts/validation/test_docs_only_eligibility.py"],
        "source": "QA Skip Verdicts",
    },
    {
        "id": "drift-allowlist",
        "answers": "Is each drift allowlist entry valid, and does any entry match no drift?",
        "argv": ["uv", "run", "python", "build/generate_agents.py", "--validate"],
        "source": "Commit Markers",
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
