#!/usr/bin/env python3
"""Instrument table for the ai-agents-empirical-probe-toolkit skill."""

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
)
from scripts.instrument_cli import (
    python_target as _target,
)

SKILL = "ai-agents-empirical-probe-toolkit"
_HERE = f".claude/skills/{SKILL}"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "eval-flags",
        "answers": "Does every eval-harness flag the skill names exist in the script it is attributed to?",
        "argv": ["python3", f"{_HERE}/scripts/cli_flags_check.py", "--repo", "."],
        "source": "Recipe 3",
    },
    {
        "id": "cited-paths",
        "answers": "Do the repo paths this skill cites still exist? (path existence only, not line content)",
        "argv": [
            "python3",
            ".claude/skills/skill-bootstrap/scripts/bootstrap_mine.py",
            "claims",
            "--repo",
            ".",
            f"{_HERE}/SKILL.md",
            f"{_HERE}/references/worked-examples.md",
        ],
        "source": "whole skill",
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


_HELP_EPILOG = instrument_epilog("eval-flags")


_dispatcher = InstrumentDispatcher(
    InstrumentHelp(SKILL, instrument_description(__doc__ or ""), _HELP_EPILOG, "examined"),
    lambda: INSTRUMENTS,
    lambda repo, row: (target := _target(row["argv"])) is None or (repo / target).is_file(),
)
main = _dispatcher.main
cmd_list = _dispatcher.cmd_list
cmd_run = _dispatcher.cmd_run
build_parser = _dispatcher.build_parser


if __name__ == "__main__":
    sys.exit(main())
