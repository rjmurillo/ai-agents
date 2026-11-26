#!/usr/bin/env python3
"""Instrument table for ai-agents-docs-of-record."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.instrument_cli import (
    InstrumentDispatcher,
    InstrumentHelp,
    instrument_epilog,
    python_script_exists,
)

SKILL = "ai-agents-docs-of-record"
SK = ".claude/skills"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "adr-next-number",
        "answers": "What is the next free ADR number, and do ADR numbers collide?",
        "argv": ["python3", "scripts/validation/check_adr_uniqueness.py", "--print-next"],
        "source": "SKILL.md ADR section and Provenance",
    },
    {
        "id": "retro-index-coverage",
        "answers": "How many retro files exist and how many does INDEX.md cover?",
        "argv": [
            "python3",
            f"{SK}/ai-agents-failure-archaeology/scripts/corpus_index.py",
            "--repo",
            ".",
        ],
        "source": "SKILL.md Provenance and Maintenance",
    },
    {
        "id": "session-log-validate",
        "answers": "Does a historical session log pass the filename, branch, and schema checks?",
        "argv": ["uv", "run", "python", "scripts/validate_session_json.py"],
        "source": "SKILL.md Phase 2",
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


_HELP_EPILOG = instrument_epilog("adr-next-number")


_dispatcher = InstrumentDispatcher(
    InstrumentHelp(SKILL, __doc__ or "", _HELP_EPILOG, "json"),
    lambda: INSTRUMENTS,
    python_script_exists,
)
main = _dispatcher.main
cmd_list = _dispatcher.cmd_list
cmd_run = _dispatcher.cmd_run
build_parser = _dispatcher.build_parser


if __name__ == "__main__":
    sys.exit(main())
