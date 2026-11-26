#!/usr/bin/env python3
"""Instrument table for the ai-agents-validation-and-qa skill."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.instrument_cli import (
    InstrumentDispatcher,
    InstrumentHelp,
    inline_script_exists,
    instrument_epilog,
)

SKILL = "ai-agents-validation-and-qa"
SK = ".claude/skills"
_HERE = f"{SK}/{SKILL}/scripts"

_ALLOWLIST_ARGV = [
    "python3",
    "-c",
    "import sys; sys.path.insert(0, '.'); "
    "from scripts.modules.investigation_allowlist import "
    "get_investigation_allowlist_display as g; "
    "r = g(); print(len(r)); print('\\n'.join(r))",
]
_SKIP_CODE = (
    "import ast,sys;t=ast.parse(open(sys.argv[1],encoding='utf-8').read());"
    "d=[n.value for n in ast.walk(t) if isinstance(n,ast.Assign) and "
    "any(getattr(x,'id','')=='_QA_SKIP_CHECKERS' for x in n.targets)];"
    "print('\\n'.join(ast.literal_eval(d[0]).keys()) if d else '')"
)

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "citation-freshness",
        "answers": "Do path:line citations on added lines still point at the cited content?",
        "argv": ["python3", "scripts/validation/check_citation_freshness.py"],
        "source": "Provenance and Maintenance",
    },
    {
        "id": "investigation-allowlist",
        "answers": "Which patterns hold the investigation-only allowlist? Owned by ai-agents-change-control; same argv.",
        "argv": _ALLOWLIST_ARGV,
        "check_path": "scripts/modules/investigation_allowlist.py",
        "source": "Phase 5",
    },
    {
        "id": "qa-skip-evidence",
        "answers": "Which QA skip evidence strings does the session validator accept?",
        "argv": ["python3", "-c", _SKIP_CODE, "scripts/validate_session_json.py"],
        "source": "Phase 5",
    },
    {
        "id": "pester-count",
        "answers": "How many *.Tests.ps1 files exist, and is the Pester warning still live?",
        "argv": ["python3", f"{_HERE}/test_layout.py", "--repo", ".", "pester"],
        "source": "Phase 2",
    },
    {
        "id": "skill-tests",
        "answers": "Which test files does pytest collect by default for a skill? Pass NAME.",
        "argv": ["python3", f"{_HERE}/test_layout.py", "--repo", ".", "skill-tests"],
        "source": "Phase 2 and Phase 6",
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
        "source": "Provenance and Maintenance",
    },
]


_HELP_EPILOG = instrument_epilog("citation-freshness")


_dispatcher = InstrumentDispatcher(
    InstrumentHelp(SKILL, __doc__ or "", _HELP_EPILOG, "json"),
    lambda: INSTRUMENTS,
    inline_script_exists,
)
main = _dispatcher.main
cmd_list = _dispatcher.cmd_list
cmd_run = _dispatcher.cmd_run
build_parser = _dispatcher.build_parser


if __name__ == "__main__":
    sys.exit(main())
