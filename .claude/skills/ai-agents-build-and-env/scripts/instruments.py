#!/usr/bin/env python3
"""Instrument table for the ai-agents-build-and-env skill."""

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

SKILL = "ai-agents-build-and-env"
_HERE = ".claude/skills/ai-agents-build-and-env/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "env-pins",
        "answers": "What are the interpreter, lefthook, PyYAML, requires-python, Node major, and syntax floor pins right now?",
        "argv": ["python3", f"{_HERE}/env_probe.py", "--repo", ".", "pins"],
        "source": "Phase 1 and Known Traps",
    },
    {
        "id": "env-file",
        "answers": "Does .env exist, stay untracked, and which keys does .env.example list?",
        "argv": ["python3", f"{_HERE}/env_probe.py", "--repo", ".", "envfile"],
        "source": "Phase 4 and Verification",
    },
    {
        "id": "env-smoke",
        "answers": "Do lefthook version, check-install, and the tests/test_paths.py collection pass?",
        "argv": ["python3", f"{_HERE}/env_probe.py", "--repo", ".", "smoke"],
        "source": "Phase 3 and Verification",
    },
    {
        "id": "venv-stale-check",
        "answers": "Is a moved worktree's .venv launcher shebang stale?",
        "argv": ["uv", "run", "python", "scripts/maintenance/repair_worktree_venv.py", "--check"],
        "source": "Known Traps",
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


_HELP_EPILOG = instrument_epilog("env-pins")


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
