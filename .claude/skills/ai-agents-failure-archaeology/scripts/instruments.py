#!/usr/bin/env python3
"""Instrument table for ai-agents-failure-archaeology."""

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

SKILL = "ai-agents-failure-archaeology"
SK = ".claude/skills"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "corpus-index",
        "answers": "How many retros exist, how many INDEX.md covers, how many failure modes and memories?",
        "argv": ["python3", f"{SK}/{SKILL}/scripts/corpus_index.py", "--repo", "."],
        "source": "SKILL.md Provenance and Maintenance",
    },
    {
        "id": "sha-resolve",
        "answers": "Do the retro-cited short SHAs ddb76e0 and 01e76615a resolve locally?",
        "argv": [
            "python3",
            f"{SK}/{SKILL}/scripts/corpus_index.py",
            "--repo",
            ".",
            "--shas",
            "ddb76e0",
            "01e76615a",
        ],
        "source": "SKILL.md Phase 4 item 4",
    },
    {
        "id": "path-claims",
        "answers": "Do the paths this skill cites still exist?",
        "argv": [
            "python3",
            f"{SK}/skill-bootstrap/scripts/bootstrap_mine.py",
            "claims",
            "--repo",
            ".",
            f"{SK}/{SKILL}",
        ],
        "source": "SKILL.md Verification",
    },
    {
        "id": "citation-freshness",
        "answers": "Do path:line citations on added lines still hold at HEAD?",
        "argv": ["python3", "scripts/validation/check_citation_freshness.py"],
        "source": "SKILL.md Verification",
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
