"""Fixtures shared by the skillforge triage tests (issue #6647)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.skills.skillforge.triage_support import REPO_SKILLS_DIR, discover_skills


@pytest.fixture(scope="module")
def real_index(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Index built by discover_skills.py over .claude/skills, with HOME isolated."""
    if not REPO_SKILLS_DIR.is_dir():
        pytest.skip("repo .claude/skills tree not present")
    home = tmp_path_factory.mktemp("home")
    patch = pytest.MonkeyPatch()
    try:
        patch.setenv("HOME", str(home))
        patch.setattr(
            discover_skills,
            "SKILL_SOURCES",
            [
                {
                    "name": "custom",
                    "path": REPO_SKILLS_DIR,
                    "pattern": "*/[Ss][Kk][Ii][Ll][Ll].[Mm][Dd]",
                    "priority": 1,
                }
            ],
        )
        result = discover_skills.discover_skills()
    finally:
        patch.undo()
    assert result.success
    assert result.data["total_count"] > 10
    return result.data
