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
from typing import Any

SKILL = "ai-agents-config-catalog"
_HERE = ".claude/skills/ai-agents-config-catalog/scripts"
_HOOKS = ".claude/skills/ai-agents-portability-campaign/scripts/hook_inventory.py"
_DRIFT = ".claude/skills/skill-bootstrap/scripts/bootstrap_drift.py"


def _row(id_: str, answers: str, argv: str, source: str) -> dict[str, Any]:
    """Build one instrument row from a space-separated command line."""
    return {"id": id_, "answers": answers, "argv": argv.split(), "source": source}


INSTRUMENTS: list[dict[str, Any]] = [
    _row(
        "flag-locate",
        "Which file:line defines this flag, marker, or env var? Pass an id after --, or --list.",
        f"python3 {_HERE}/flag_locator.py --repo . locate",
        "Process step 4 and Provenance and Maintenance",
    ),
    _row(
        "pytest-markers",
        "Which pytest markers does pyproject.toml declare?",
        f"python3 {_HERE}/flag_locator.py --repo . markers",
        "Environment Variables: Tests and Tooling",
    ),
    _row(
        "retired-flags",
        "Are the retired flags absent from CONTRIBUTING.md and pre_pr.py?",
        f"python3 {_HERE}/flag_locator.py --repo . retired",
        "Removed and Stale Flags",
    ),
    _row(
        "hook-counts",
        "How many events and registrations does each hook surface hold?",
        f"python3 {_HOOKS} --repo . counts",
        "Hook Registration Surfaces",
    ),
    _row(
        "manifest-version",
        "Does any plugin manifest or marketplace entry carry a version field?",
        "uv run python build/scripts/validate_plugin_version_bump.py",
        "Plugin Manifest Version Prohibition",
    ),
    _row(
        "lefthook-validate",
        "Are the Git hook jobs, filters, and validators in lefthook.yml valid?",
        "uv run --frozen lefthook validate",
        "Git Hook Configuration",
    ),
    _row(
        "qa-investigation-eligible",
        "Do the staged files qualify for SKIPPED: investigation-only?",
        "uv run python scripts/validation/test_investigation_eligibility.py",
        "QA Skip Verdicts",
    ),
    _row(
        "qa-docs-only-eligible",
        "Do the staged files qualify for SKIPPED: docs-only?",
        "uv run python scripts/validation/test_docs_only_eligibility.py",
        "QA Skip Verdicts",
    ),
    _row(
        "drift-allowlist",
        "Is each drift allowlist entry valid, and does any entry match no drift?",
        "uv run python build/generate_agents.py --validate",
        "Commit Markers",
    ),
    _row(
        "drift-self-check",
        "Does this skill's reverify.json still hold at HEAD?",
        f"python3 {_DRIFT} check --repo . --skills-root .claude/skills --name {SKILL} --require",
        "Provenance and Maintenance",
    ),
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
        sys.stdout.flush()
        return subprocess.run(row["argv"] + extra, cwd=repo, check=False).returncode
    except OSError as exc:
        print(
            json.dumps({"error": f"cannot start {row['argv'][0]}: {exc}", "examined": len(rows)}),
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
