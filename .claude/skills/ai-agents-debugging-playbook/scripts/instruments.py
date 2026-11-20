#!/usr/bin/env python3
"""Instrument table for ai-agents-debugging-playbook."""

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

SKILL = "ai-agents-debugging-playbook"
SK = ".claude/skills"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "first-command-stash",
        "answers": "Which git stash entries are foreign (WIP branch not checked out in any worktree)?",
        "argv": ["python3", f"{SK}/{SKILL}/scripts/first_command.py", "--repo", ".", "stash"],
        "source": "SKILL.md Shared checkout",
    },
    {
        "id": "first-command-lag",
        "answers": "How far does HEAD lag origin/main (left and right commit counts)?",
        "argv": ["python3", f"{SK}/{SKILL}/scripts/first_command.py", "--repo", ".", "lag"],
        "source": "SKILL.md Shared checkout",
    },
    {
        "id": "plugin-version-bump",
        "answers": "Does any plugin manifest or marketplace entry carry a version field?",
        "argv": ["python3", "build/scripts/validate_plugin_version_bump.py"],
        "source": "SKILL.md CI reds",
    },
    {
        "id": "dash-scan",
        "answers": "Do changed files carry an em or en dash?",
        "argv": [
            "uv",
            "run",
            "python",
            "scripts/validation/git_hook_policy.py",
            "branch-dashes",
        ],
        "source": "SKILL.md Local blocks",
    },
    {
        "id": "spec-id-uniqueness",
        "answers": "Are REQ and TASK spec ids unique in the working tree?",
        "argv": ["python3", "scripts/validation/check_spec_id_uniqueness.py"],
        "source": "SKILL.md Shared checkout",
    },
    {
        "id": "python-syntax",
        "answers": "Does every tracked Python file parse at the 3.10 floor?",
        "argv": ["python3", "scripts/validation/validate_python_syntax.py"],
        "source": "SKILL.md CI reds",
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


_HELP_EPILOG = instrument_epilog("first-command-stash")


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
