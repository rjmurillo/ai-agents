"""Tests for validate_marketplace_counts module.

Validates that the marketplace.json count validator correctly parses
description strings, counts source directory contents, and detects
mismatches between declared and actual counts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BUILD_SCRIPTS = Path(__file__).resolve().parent.parent / "build" / "scripts"
sys.path.insert(0, str(_BUILD_SCRIPTS))

from validate_marketplace_counts import (  # noqa: E402
    parse_counts_from_description,
    validate,
)


class TestParseCountsFromDescription:
    """Verify count extraction from plugin description strings."""

    def test_single_agent_count(self) -> None:
        desc = "23 specialized agent definitions with governance"
        result = parse_counts_from_description(desc)
        assert result == {"agent": 23}

    def test_plain_agent_count(self) -> None:
        desc = "23 agent definitions for GitHub Copilot CLI"
        result = parse_counts_from_description(desc)
        assert result == {"agent": 23}

    def test_multiple_counts(self) -> None:
        desc = (
            "Complete toolkit: 10 agents, 5 slash commands, "
            "8 lifecycle hooks, and 20 reusable skills"
        )
        result = parse_counts_from_description(desc)
        assert result == {
            "agent": 10,
            "slash command": 5,
            "lifecycle hook": 8,
            "reusable skill": 20,
        }

    def test_no_counts(self) -> None:
        desc = "A simple description with no counts"
        result = parse_counts_from_description(desc)
        assert result == {}

    def test_singular_form(self) -> None:
        desc = "1 agent and 1 slash command"
        result = parse_counts_from_description(desc)
        assert result == {"agent": 1, "slash command": 1}


class TestValidateIntegration:
    """Integration test against the real repo structure."""

    def test_current_counts_are_valid(self) -> None:
        """After --fix, the marketplace.json should pass validation."""
        assert validate(fix=False) == 0


class TestValidateWithFixtures:
    """Test validation logic with temporary marketplace.json files."""

    def test_detects_stale_count(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        marketplace = tmp_path / ".claude-plugin" / "marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(
            json.dumps(
                {
                    "plugins": [
                        {
                            "name": "claude-agents",
                            "description": "999 specialized agent definitions",
                            "source": "./src/claude",
                        }
                    ]
                }
            )
        )
        monkeypatch.setattr(
            "validate_marketplace_counts.MARKETPLACE_JSON", marketplace
        )
        assert validate(fix=False) == 1

    def test_fix_updates_count(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        marketplace = tmp_path / ".claude-plugin" / "marketplace.json"
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(
            json.dumps(
                {
                    "plugins": [
                        {
                            "name": "claude-agents",
                            "description": "999 specialized agent definitions",
                            "source": "./src/claude",
                        }
                    ]
                }
            )
        )
        monkeypatch.setattr(
            "validate_marketplace_counts.MARKETPLACE_JSON", marketplace
        )
        assert validate(fix=True) == 0

        data = json.loads(marketplace.read_text())
        desc = data["plugins"][0]["description"]
        assert "999" not in desc
        assert "23 specialized agent definitions" in desc

    def test_missing_marketplace_returns_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "validate_marketplace_counts.MARKETPLACE_JSON",
            tmp_path / "nonexistent.json",
        )
        assert validate(fix=False) == 2
