#!/usr/bin/env python3
"""Instrument table for the repository-pr-recovery skill."""

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

SKILL = "repository-pr-recovery"
_GH = ".claude/skills/github/scripts/pr"
_HERE = ".claude/skills/repository-pr-recovery/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "why-pr-blocked",
        "answers": "Which diagnosed causes block this PR (checks, threads, conflicts)?",
        "argv": ["python3", f"{_GH}/why_pr_blocked.py"],
        "source": "Phase 1",
    },
    {
        "id": "triage-red-check",
        "answers": "Is this red check inherited from the base branch (GREEN_ON_MAIN, RED_ON_MAIN, PR_ONLY, CANCELLED_ON_MAIN, UNKNOWN)?",
        "argv": ["python3", f"{_GH}/triage_red_check.py"],
        "source": "Phase 1",
    },
    {
        "id": "check-logs",
        "answers": "What do the logs of a failed check say?",
        "argv": ["python3", f"{_GH}/get_pr_check_logs.py"],
        "source": "Phase 1",
    },
    {
        "id": "review-threads",
        "answers": "Which review threads exist and which are unresolved?",
        "argv": ["python3", f"{_GH}/get_pr_review_threads.py"],
        "source": "Phase 1",
    },
    {
        "id": "required-context-conditions",
        "answers": "Do workflows that produce a pinned required context hide step conditions that skip the verification?",
        "argv": ["uv", "run", "python", "scripts/validation/check_required_context_conditions.py"],
        "source": "Phase 2",
    },
    {
        "id": "producer-join",
        "answers": "Is each required context produced by its required app on the evaluated SHA?",
        "argv": ["python3", f"{_HERE}/required_check_producer_join.py", "--repo", "."],
        "source": "Phase 2",
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


_HELP_EPILOG = instrument_epilog("why-pr-blocked -- --pull-request 123")


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
