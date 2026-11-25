#!/usr/bin/env python3
"""Instrument table for ai-agents-research-frontier."""

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

SKILL = "ai-agents-research-frontier"
SK = ".claude/skills"

COUNTS_CODE = (
    "import glob,json;"
    "print(json.dumps({"
    "'skills':len(glob.glob('.claude/skills/*/SKILL.md')),"
    "'rules':len(glob.glob('.claude/rules/*.md')),"
    "'rule_scenarios':len(glob.glob('tests/evals/rule-scenarios/*')),"
    "'retros':len([f for f in glob.glob('.project-toolkit/retrospective/*.md')"
    " if not f.endswith('INDEX.md')]),"
    "'memories_recursive_md':len(glob.glob('.serena/memories/**/*.md',recursive=True))}))"
)

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "corpus-counts",
        "answers": "How many skills, rules, rule scenario fixtures, retros, and memories exist now?",
        "argv": ["python3", "-c", COUNTS_CODE],
        "source": "SKILL.md Phase 1",
    },
    {
        "id": "corpus-index",
        "answers": "How many retros exist, how many INDEX.md covers, how many failure modes and memories?",
        "argv": [
            "python3",
            ".claude/skills/ai-agents-failure-archaeology/scripts/corpus_index.py",
            "--repo",
            ".",
        ],
        "source": "SKILL.md Phase 1",
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


_HELP_EPILOG = instrument_epilog("corpus-counts")


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
