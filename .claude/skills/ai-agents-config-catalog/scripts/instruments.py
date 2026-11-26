#!/usr/bin/env python3
"""Instrument table for the ai-agents-config-catalog skill."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.instrument_cli import (
    InstrumentDispatcher,
    InstrumentHelp,
    instrument_description,
    instrument_epilog,
    target_exists,
)

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


_HELP_EPILOG = instrument_epilog("flag-locate -- --list")


_dispatcher = InstrumentDispatcher(
    InstrumentHelp(SKILL, instrument_description(__doc__ or ""), _HELP_EPILOG, "examined"),
    lambda: INSTRUMENTS,
    target_exists,
)
main = _dispatcher.main
cmd_list = _dispatcher.cmd_list
cmd_run = _dispatcher.cmd_run
build_parser = _dispatcher.build_parser


if __name__ == "__main__":
    sys.exit(main())
