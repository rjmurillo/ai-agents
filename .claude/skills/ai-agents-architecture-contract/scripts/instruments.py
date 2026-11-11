#!/usr/bin/env python3
"""Instrument dispatcher for the ai-agents-architecture-contract skill."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.instrument_cli import (
    InstrumentDispatcher,
    InstrumentHelp,
    drift_instrument,
    instrument_epilog,
    instrument_row,
    repo_paths_exist,
)

SKILL = "ai-agents-architecture-contract"
SCRIPTS = f".claude/skills/{SKILL}/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    instrument_row(
        "adr-status",
        "What are the status, superseded-by, and implemented flag of each cited ADR?",
        f"python3 {SCRIPTS}/contract_probe.py --repo . adrs",
        "Phase 2 and references/adr-decisions.md",
    ),
    instrument_row(
        "guard-lines",
        "Where are assert_no_claude_writes and its call sites?",
        f"python3 {SCRIPTS}/contract_probe.py --repo . guard",
        "Phase 1 direction rule",
    ),
    instrument_row(
        "hook-counts",
        "How many hook events and registrations does each hook manifest hold?",
        "python3 .claude/skills/ai-agents-portability-campaign/scripts/hook_inventory.py --repo . counts",
        "Phase 3 registration split",
    ),
    instrument_row(
        "generator-path",
        "Which tree is canonical for a repo path, and what regenerates it? Pass the path after --.",
        "python3 .claude/skills/ai-agents-generation-and-release/scripts/generator_inventory.py --repo . path",
        "Phase 1 source-of-truth table",
    ),
    instrument_row(
        "version-gate",
        "Does any plugin manifest or marketplace entry carry a version field?",
        "python3 build/scripts/validate_plugin_version_bump.py",
        "Phase 5 plugin surfaces",
    ),
    instrument_row(
        "claims",
        "Which paths and test node ids cited by this skill no longer exist?",
        "python3 .claude/skills/skill-bootstrap/scripts/bootstrap_mine.py claims --repo . .claude/skills/ai-agents-architecture-contract",
        "references/provenance.md",
    ),
    {**drift_instrument(SKILL, SCRIPTS.rsplit("/", 2)[0]), "source": "Provenance and Maintenance"},
]


_HELP_EPILOG = instrument_epilog("adr-status")


_dispatcher = InstrumentDispatcher(
    InstrumentHelp(SKILL, __doc__ or "", _HELP_EPILOG, "plain"),
    lambda: INSTRUMENTS,
    repo_paths_exist,
)
main = _dispatcher.main
cmd_list = _dispatcher.cmd_list
cmd_run = _dispatcher.cmd_run
build_parser = _dispatcher.build_parser


if __name__ == "__main__":
    sys.exit(main())
