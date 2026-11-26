#!/usr/bin/env python3
"""Instrument table for the repository-consumer-proof skill."""

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
    test_target_exists,
)

SKILL = "repository-consumer-proof"
_HERE = ".claude/skills/repository-consumer-proof/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "generated-output-check",
        "answers": "Does generated output match templates and committed state?",
        "argv": ["uv", "run", "python", "build/scripts/build_all.py", "--check"],
        "source": "Phase 2 generation step",
    },
    {
        "id": "installed-dispatcher",
        "answers": "Did the installed completion dispatcher run its bundled criteria end to end?",
        "argv": ["uv", "run", "pytest", "tests/test_run_completion_gate_install.py", "-q"],
        "source": "Phase 2 installed dispatcher",
    },
    {
        "id": "hook-runtime-contract",
        "answers": "Do hooks run from a foreign cwd and do plugin-root variables resolve?",
        "argv": [
            "uv",
            "run",
            "pytest",
            "tests/build_scripts/test_generate_hooks_runtime_contract.py",
            "tests/build_scripts/test_generate_hooks_plugin_root.py",
            "-q",
        ],
        "source": "Phase 2 hook suites",
    },
    {
        "id": "runtime-parity-dry-run",
        "answers": "Do the completion-terminal parity fixtures pass their deterministic controls? Caller passes `-- --model <id>`.",
        "argv": [
            "uv",
            "run",
            "python",
            "scripts/eval/eval_runtime_parity.py",
            "--fixtures",
            "tests/evals/completion-terminal-runtime-fixtures.json",
            "--harnesses",
            "claude",
            "--dry-run",
        ],
        "source": "Phase 3 dry-run",
    },
    {
        "id": "artifact-owner",
        "answers": "Which layer and binplace row own a given repo path?",
        "argv": ["python3", f"{_HERE}/artifact_owner.py", "--repo", "."],
        "source": "Phase 1 generated artifacts",
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


_HELP_EPILOG = instrument_epilog("generated-output-check")


_dispatcher = InstrumentDispatcher(
    InstrumentHelp(SKILL, instrument_description(__doc__ or ""), _HELP_EPILOG, "examined"),
    lambda: INSTRUMENTS,
    test_target_exists,
)
main = _dispatcher.main
cmd_list = _dispatcher.cmd_list
cmd_run = _dispatcher.cmd_run
build_parser = _dispatcher.build_parser


if __name__ == "__main__":
    sys.exit(main())
