#!/usr/bin/env python3
"""Instrument dispatcher for the ai-agents-generation-and-release skill."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.instrument_cli import (
    InstrumentDispatcher,
    InstrumentHelp,
    instrument_epilog,
    repo_paths_exist,
)

SKILL = "ai-agents-generation-and-release"
SCRIPTS = f".claude/skills/{SKILL}/scripts"

INSTRUMENTS: list[dict[str, Any]] = [
    {
        "id": "generators",
        "answers": "Which generators does build_all.py run, in what order, and what are OWNED_PREFIXES?",
        "argv": ["python3", f"{SCRIPTS}/generator_inventory.py", "--repo", ".", "generators"],
        "source": "Phase 1 Know the Seam",
    },
    {
        "id": "path",
        "answers": "Which tree is canonical for a repo path, and what regenerates it? Pass the path after --.",
        "argv": ["python3", f"{SCRIPTS}/generator_inventory.py", "--repo", ".", "path"],
        "source": "Phase 1 Know the Seam",
    },
    {
        "id": "skills",
        "answers": "How many skill templates exist and which skills are repo-local?",
        "argv": ["python3", f"{SCRIPTS}/generator_inventory.py", "--repo", ".", "skills"],
        "source": "Phase 1 Know the Seam",
    },
    {
        "id": "gates",
        "answers": "Which lefthook job or workflow job runs each drift gate?",
        "argv": ["python3", f"{SCRIPTS}/generator_inventory.py", "--repo", ".", "gates"],
        "source": "Phase 3 Drift gates",
    },
    {
        "id": "build-all-check",
        "answers": "Is any generated tree stale against its canonical source?",
        "argv": ["uv", "run", "python", "build/scripts/build_all.py", "--check"],
        "source": "Phase 3 Drift gates",
    },
    {
        "id": "version-field",
        "answers": "Does any plugin manifest or marketplace entry carry a version field?",
        "argv": ["python3", "build/scripts/validate_plugin_version_bump.py"],
        "source": "Phase 4 Plugin manifests",
    },
    {
        "id": "manifest-parity",
        "answers": "Do the plugin manifest descriptions agree on component counts?",
        "argv": ["python3", "build/scripts/check_plugin_manifest_parity.py"],
        "source": "Phase 4 Plugin manifests",
    },
    {
        "id": "drift-self-check",
        "answers": "Has this skill drifted from its reverify.json checks?",
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


_HELP_EPILOG = instrument_epilog("generators")


_dispatcher = InstrumentDispatcher(
    InstrumentHelp(SKILL, __doc__ or "", _HELP_EPILOG, "plain"),
    lambda: INSTRUMENTS,
    repo_paths_exist,
)
main = _dispatcher.main
cmd_list = _dispatcher.cmd_list
cmd_run = _dispatcher.cmd_run
build_parser = _dispatcher.build_parser


if __name__ == "__main__":
    sys.exit(main())
