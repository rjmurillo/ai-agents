#!/usr/bin/env python3
"""Instrument table for ai-agents-research-methodology."""

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
    python_script_exists,
)

SKILL = "ai-agents-research-methodology"
SK = ".claude/skills"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "corpus-index",
        "answers": "How many retro files exist, and how many does INDEX.md cover?",
        "argv": [
            "python3",
            f"{SK}/ai-agents-failure-archaeology/scripts/corpus_index.py",
            "--repo",
            ".",
        ],
        "source": "SKILL.md Provenance and Maintenance",
    },
    {
        "id": "path-claims",
        "answers": "Do the paths and file:line references this skill cites still hold?",
        "argv": [
            "python3",
            f"{SK}/skill-bootstrap/scripts/bootstrap_mine.py",
            "claims",
            "--repo",
            ".",
            f"{SK}/{SKILL}",
        ],
        "source": "SKILL.md Provenance and Maintenance",
    },
    {
        "id": "citation-freshness",
        "answers": "Do path:line citations on added lines still hold at HEAD?",
        "argv": ["python3", "scripts/validation/check_citation_freshness.py"],
        "source": "SKILL.md Provenance and Maintenance",
    },
    {
        "id": "citation-reverse-pass",
        "answers": "Do citations on unchanged lines still hold for files this branch changed?",
        "argv": ["python3", "scripts/validation/citation_reverse_pass.py"],
        "source": "SKILL.md Provenance and Maintenance",
    },
    drift_instrument(SKILL, SK),
]


_HELP_EPILOG = instrument_epilog("corpus-index")


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
