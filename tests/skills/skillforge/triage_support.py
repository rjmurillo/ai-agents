"""Shared setup for the skillforge triage tests (issue #6647)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skillforge" / "scripts"
# skillforge/scripts holds a frontmatter.py that shadows the PyPI package, so
# restore sys.path once the import is done.
_SAVED_SYS_PATH = list(sys.path)
sys.path.insert(0, str(SCRIPTS_DIR))
import triage_skill_request as triage

sys.path[:] = _SAVED_SYS_PATH

CREATE_QUERY = (
    "create a skill for running a social media hook testing loop "
    "with time-slot rotation and click-through scoring"
)
BARE_QUERY = "social media hook testing loop"


def make_skill(
    name: str,
    description: str,
    keywords: list[str] | None = None,
    domains: list[str] | None = None,
    triggers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "source": "fixture",
        "description": description,
        "keywords": keywords or [],
        "domains": domains or [],
        "triggers": triggers or [],
    }


def run_triage(query: str) -> dict[str, Any]:
    result = triage.triage_request(query)
    assert result.success
    return result.data
