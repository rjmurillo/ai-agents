"""Tests for SkillForge frontmatter property allowlist (_constants).

Guards the set of allowed SKILL.md frontmatter properties. Regression for the
case where a user-invocable command-skill (e.g. /review) declares the standard
Claude Code ``argument-hint`` field and the validator rejected it as an
unexpected property. Refs #2302.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent
_SCRIPT_DIR = _TEST_DIR.parent / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

from _constants import ALLOWED_PROPERTIES, OPTIONAL_PROPERTIES  # noqa: E402


class TestAllowedProperties:
    def test_argument_hint_is_allowed(self) -> None:
        # Standard Claude Code slash-command field; command-skills declare it.
        assert "argument-hint" in ALLOWED_PROPERTIES

    def test_argument_hint_is_optional_not_required(self) -> None:
        assert "argument-hint" in OPTIONAL_PROPERTIES

    def test_core_required_fields_still_allowed(self) -> None:
        # Adding a field must not drop existing ones.
        for field in ("name", "description", "user-invocable", "version"):
            assert field in ALLOWED_PROPERTIES
