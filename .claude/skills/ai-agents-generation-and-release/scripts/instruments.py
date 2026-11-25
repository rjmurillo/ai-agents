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
    drift_instrument,
    instrument_epilog,
    instrument_row,
    repo_paths_exist,
)

SKILL = "ai-agents-generation-and-release"
SCRIPTS = f".claude/skills/{SKILL}/scripts"


def _inventory_instrument(
    command: str, answers: str, source: str = "Phase 1 Know the Seam"
) -> dict[str, Any]:
    return instrument_row(
        command, answers, f"python3 {SCRIPTS}/generator_inventory.py --repo . {command}", source
    )


INSTRUMENTS: list[dict[str, Any]] = [
    _inventory_instrument(command, question)
    for command, question in {
        "generators": "Which generators does build_all.py run, in what order, and what are OWNED_PREFIXES?",
        "path": "Which tree is canonical for a repo path, and what regenerates it? Pass the path after --.",
        "skills": "How many skill templates exist and which skills are repo-local?",
    }.items()
] + [
    _inventory_instrument(
        "gates",
        "Which lefthook job or workflow job runs each drift gate?",
        "Phase 3 Drift gates",
    ),
    instrument_row(
        "build-all-check",
        "Is any generated tree stale against its canonical source?",
        "uv run python build/scripts/build_all.py --check",
        "Phase 3 Drift gates",
    ),
    instrument_row(
        "version-field",
        "Does any plugin manifest or marketplace entry carry a version field?",
        "python3 build/scripts/validate_plugin_version_bump.py",
        "Phase 4 Plugin manifests",
    ),
    instrument_row(
        "manifest-parity",
        "Do the plugin manifest descriptions agree on component counts?",
        "python3 build/scripts/check_plugin_manifest_parity.py",
        "Phase 4 Plugin manifests",
    ),
    {**drift_instrument(SKILL, SCRIPTS.rsplit("/", 2)[0]), "source": "Provenance and Maintenance"},
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
