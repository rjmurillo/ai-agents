#!/usr/bin/env python3
"""Instrument dispatcher for the ai-agents-portability-campaign skill."""

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

SKILL = "ai-agents-portability-campaign"
SCRIPTS = f".claude/skills/{SKILL}/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "hook-counts",
        "answers": "How many hook events and registrations does each hook manifest hold?",
        "argv": ["python3", f"{SCRIPTS}/hook_inventory.py", "--repo", ".", "counts"],
        "source": "Phase 4 Inventories",
    },
    {
        "id": "phase-tests",
        "answers": "Does every pytest path the skill names exist?",
        "argv": ["python3", f"{SCRIPTS}/hook_inventory.py", "--repo", ".", "phase-tests"],
        "source": "Phase 3 and Phase 5",
    },
    {
        "id": "qualifiers",
        "answers": "Does every shipped reference to this skill carry the ai-agents repository qualifier?",
        "argv": ["python3", f"{SCRIPTS}/hook_inventory.py", "--repo", ".", "qualifiers"],
        "source": "Authority boundary",
    },
    {
        "id": "event-map",
        "answers": "Which Claude event maps to which Copilot event (eventRemap)?",
        "argv": ["grep", "-n", "-A12", "eventRemap:", "templates/platforms/copilot-cli.yaml"],
        "source": "Phase 1 event mapping",
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


_HELP_EPILOG = instrument_epilog("hook-counts")


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
