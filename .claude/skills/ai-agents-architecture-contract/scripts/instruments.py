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
    instrument_epilog,
    repo_paths_exist,
)

SKILL = "ai-agents-architecture-contract"
SCRIPTS = f".claude/skills/{SKILL}/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "adr-status",
        "answers": "What are the status, superseded-by, and implemented flag of each cited ADR?",
        "argv": ["python3", f"{SCRIPTS}/contract_probe.py", "--repo", ".", "adrs"],
        "source": "Phase 2 and references/adr-decisions.md",
    },
    {
        "id": "guard-lines",
        "answers": "Where are assert_no_claude_writes and its call sites?",
        "argv": ["python3", f"{SCRIPTS}/contract_probe.py", "--repo", ".", "guard"],
        "source": "Phase 1 direction rule",
    },
    {
        "id": "hook-counts",
        "answers": "How many hook events and registrations does each hook manifest hold?",
        "argv": [
            "python3",
            ".claude/skills/ai-agents-portability-campaign/scripts/hook_inventory.py",
            "--repo",
            ".",
            "counts",
        ],
        "source": "Phase 3 registration split",
    },
    {
        "id": "generator-path",
        "answers": "Which tree is canonical for a repo path, and what regenerates it? Pass the path after --.",
        "argv": [
            "python3",
            ".claude/skills/ai-agents-generation-and-release/scripts/generator_inventory.py",
            "--repo",
            ".",
            "path",
        ],
        "source": "Phase 1 source-of-truth table",
    },
    {
        "id": "version-gate",
        "answers": "Does any plugin manifest or marketplace entry carry a version field?",
        "argv": ["python3", "build/scripts/validate_plugin_version_bump.py"],
        "source": "Phase 5 plugin surfaces",
    },
    {
        "id": "claims",
        "answers": "Which paths and test node ids cited by this skill no longer exist?",
        "argv": [
            "python3",
            ".claude/skills/skill-bootstrap/scripts/bootstrap_mine.py",
            "claims",
            "--repo",
            ".",
            ".claude/skills/ai-agents-architecture-contract",
        ],
        "source": "references/provenance.md",
    },
    {
        "id": "drift-self-check",
        "answers": "Has this skill drifted from its reverify.json checks?",
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
