#!/usr/bin/env python3
"""Instrument table for the repository-completion-proof skill."""

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

SKILL = "repository-completion-proof"
_PR = ".claude/skills/github/scripts/pr"


def _row(id_: str, answers: str, argv: str, source: str = "Phase 2") -> dict[str, Any]:
    """Build one instrument row from a space-separated command line."""
    return {"id": id_, "answers": answers, "argv": argv.split(), "source": source}


INSTRUMENTS: list[dict[str, Any]] = [
    _row(
        "verify-config",
        "Are the review config and its command files trusted against the remote anchor (verified: true)?",
        f"uv run python {_PR}/run_completion_gate.py --verify-config-only --json",
        "Phase 1",
    ),
    _row(
        "merged-state",
        "Is the PR merged? Read the JSON merged field, not the exit code.",
        f"uv run python {_PR}/test_pr_merged.py",
    ),
    _row(
        "settled-zero",
        "Do three consecutive complete readings show zero unresolved threads?",
        f"uv run python {_PR}/wait_for_unresolved_zero.py",
    ),
    _row(
        "completion-gate",
        "Do all configured completion criteria pass (all_passed and per-criterion results)? Dispatches verifiers.",
        f"uv run python {_PR}/run_completion_gate.py --json",
    ),
    _row(
        "resolution-shas",
        "Are the commit SHAs cited in resolved review threads reachable?",
        f"uv run python {_PR}/check_review_thread_resolution_shas.py",
    ),
    _row(
        "suppressed-findings",
        "Are suppressed review findings dispositioned?",
        f"uv run python {_PR}/check_suppressed_review_findings.py",
    ),
    _row(
        "merge-ready",
        "Is the PR merge-ready on the live state GitHub reports?",
        f"uv run python {_PR}/test_pr_merge_ready.py",
        "Phase 3",
    ),
    _row(
        "live-state",
        "What is the PR's current live state (head, checks, threads)?",
        f"uv run python {_PR}/check_pr_live_state.py",
        "Phase 3",
    ),
    _row(
        "drift-self-check",
        "Does this skill's reverify.json still hold at HEAD?",
        f"python3 .claude/skills/skill-bootstrap/scripts/bootstrap_drift.py check --repo . --skills-root .claude/skills --name {SKILL} --require",
        "Provenance and Maintenance",
    ),
]


_HELP_EPILOG = instrument_epilog("verify-config -- --pull-request 123")


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
