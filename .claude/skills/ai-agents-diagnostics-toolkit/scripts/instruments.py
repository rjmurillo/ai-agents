#!/usr/bin/env python3
"""Instrument table for ai-agents-diagnostics-toolkit."""

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

SKILL = "ai-agents-diagnostics-toolkit"
SK = ".claude/skills"


def _row(
    id_: str, answers: str, argv: str, source: str = "SKILL.md Instrument Index"
) -> dict[str, Any]:
    """Build one instrument row from a space-separated command line."""
    return {"id": id_, "answers": answers, "argv": argv.split(), "source": source}


INSTRUMENTS: list[dict[str, Any]] = [
    _row(
        "description-budget",
        "How much standing context do skill descriptions cost?",
        "uv run python ./scripts/skill_description_budget.py --top 10",
    ),
    _row(
        "skill-size",
        "Which SKILL.md files pass the line and byte limits? (exit 0 unless --ci)",
        "uv run python ./scripts/validation/skill_size.py",
    ),
    _row(
        "orphan-refs",
        "Do specs, evals, and manifests reference entities that no longer exist?",
        f"python3 {SK}/orphan-ref-validator/scripts/scan.py",
    ),
    _row(
        "golden-principles",
        "Where does the repo violate the mechanical golden principles? (exit 10 on violations)",
        f"python3 {SK}/golden-principles/scripts/scan_principles.py",
    ),
    _row(
        "agent-drift",
        "Do generated agent files match their templates?",
        "uv run python build/generate_agents.py --validate",
    ),
    _row(
        "build-check",
        "Do generated mirror and lib trees match canonical sources? Writes build/audit/GENERATION-AUDIT.md.",
        "uv run python build/scripts/build_all.py --check",
    ),
    _row(
        "install-parity",
        "Does the install surface stay in parity across hosts (ADR-035)?",
        "uv run python scripts/validation/run_install_parity_ci.py",
    ),
    _row(
        "eval-prompt-change",
        "Did a prompt change alter behavior? Pass --prompt and --scenarios; --dry-run spends nothing.",
        "uv run python ./scripts/eval/eval-prompt-change.py --dry-run",
    ),
    _row(
        "eval-agent-vs-baseline",
        "Does an agent beat the baseline? Pass --agent and --fixtures; --dry-run is already set.",
        "uv run python ./scripts/eval/eval-agent-vs-baseline.py --dry-run",
    ),
    _row(
        "coverage",
        "Is changed code exercised by tests? With no target it runs the whole suite; pass a test path and --cov=<dotted module> after --.",
        "uv run pytest --cov-branch",
    ),
    _row(
        "commit-count",
        "How many commits is HEAD ahead of origin/main? Advisory only.",
        "git rev-list --count HEAD ^origin/main",
    ),
    _row(
        "baseline-snapshot",
        "What are the current headline numbers of the four read-only instruments?",
        f"python3 {SK}/{SKILL}/scripts/baseline_snapshot.py --repo .",
        "SKILL.md Baselines",
    ),
    drift_instrument(SKILL, SK),
]


_HELP_EPILOG = instrument_epilog("description-budget")


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
