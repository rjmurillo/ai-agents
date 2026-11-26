#!/usr/bin/env python3
"""Instrument table for ai-agents-change-control."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.instrument_cli import (
    InstrumentDispatcher,
    InstrumentHelp,
    checked_script_exists,
    instrument_epilog,
)

SKILL = "ai-agents-change-control"
SK = ".claude/skills"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "classify-change",
        "answers": "Which change class and which gates does each changed path trigger?",
        "argv": ["python3", f"{SK}/{SKILL}/scripts/classify_change.py", "--repo", ".", "--staged"],
        "source": "SKILL.md Phase 1 and Phase 2",
    },
    {
        "id": "investigation-allowlist",
        "answers": "Which patterns does the enforced investigation-only allowlist hold, and how many?",
        "argv": [
            "python3",
            "-c",
            "import sys; sys.path.insert(0, '.'); "
            "from scripts.modules.investigation_allowlist import "
            "get_investigation_allowlist_display as g; "
            "r = g(); print(len(r)); print('\\n'.join(r))",
        ],
        "check_path": "scripts/modules/investigation_allowlist.py",
        "source": "SKILL.md Phase 1",
    },
    {
        "id": "drift-agents",
        "answers": "Do generated agent files match their templates?",
        "argv": ["uv", "run", "python", "build/generate_agents.py", "--validate"],
        "check_path": "build/generate_agents.py",
        "source": "SKILL.md Phase 2",
    },
    {
        "id": "drift-build-all",
        "answers": "Do all generated trees match their canonical sources?",
        "argv": ["uv", "run", "python", "build/scripts/build_all.py", "--check"],
        "check_path": "build/scripts/build_all.py",
        "source": "SKILL.md Phase 2",
    },
    {
        "id": "plugin-version-absent",
        "answers": "Does any plugin manifest or marketplace entry carry a version field?",
        "argv": ["python3", "build/scripts/validate_plugin_version_bump.py"],
        "source": "SKILL.md Verification",
    },
    {
        "id": "dash-check",
        "answers": "Do changed .md and .py files on this branch contain em or en dashes?",
        "argv": [
            "uv",
            "run",
            "python",
            "-c",
            "import sys; sys.path.insert(0, 'scripts/validation'); "
            "from pathlib import Path; "
            "from checks_dash import validate_dash_prohibition as v; "
            "o = v(Path('.')); print(o); sys.exit(0 if o.state.name == 'PASS' else 1)",
        ],
        "check_path": "scripts/validation/checks_dash.py",
        "source": "SKILL.md Verification",
    },
    {
        "id": "citation-freshness",
        "answers": "Do path:line citations on added lines still hold at HEAD?",
        "argv": ["python3", "scripts/validation/check_citation_freshness.py"],
        "source": "SKILL.md Verification",
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


_HELP_EPILOG = instrument_epilog("classify-change")


_dispatcher = InstrumentDispatcher(
    InstrumentHelp(SKILL, __doc__ or "", _HELP_EPILOG, "json"),
    lambda: INSTRUMENTS,
    checked_script_exists,
)
main = _dispatcher.main
cmd_list = _dispatcher.cmd_list
cmd_run = _dispatcher.cmd_run
build_parser = _dispatcher.build_parser


if __name__ == "__main__":
    sys.exit(main())
