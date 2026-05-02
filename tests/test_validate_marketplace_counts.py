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
    COPILOT_MARKETPLACE_JSON,
    parse_counts_from_description,
    validate,
    validate_known_marketplaces,
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
        """Claude marketplace should pass validation."""
        assert validate(fix=False) == 0

    def test_copilot_marketplace_counts_are_valid(self) -> None:
        """Copilot marketplace should pass validation."""
        assert validate(fix=False, marketplace_path=COPILOT_MARKETPLACE_JSON) == 0

    def test_all_known_marketplaces_are_valid(self) -> None:
        """Default CLI mode validates every shipped marketplace."""
        assert validate_known_marketplaces(fix=False) == 0

    def test_known_marketplaces_resolve_paths_relative_to_repo_root(
        self, tmp_path: Path
    ) -> None:
        """`repo_root` override must steer the resolver away from the
        module-level marketplace constants. With an empty fake repo, the
        function must report a config error (exit 2) instead of silently
        validating the production manifests under the real REPO_ROOT.
        """
        assert validate_known_marketplaces(fix=False, repo_root=tmp_path) == 2


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
        assert "24 specialized agent definitions" in desc

    def test_missing_marketplace_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "validate_marketplace_counts.MARKETPLACE_JSON",
            tmp_path / "nonexistent.json",
        )
        assert validate(fix=False) == 2

    def test_malformed_json_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        marketplace = tmp_path / "marketplace.json"
        marketplace.write_text("{invalid json")
        monkeypatch.setattr(
            "validate_marketplace_counts.MARKETPLACE_JSON", marketplace
        )
        assert validate(fix=False) == 2


class TestZeroEditExtensibility:
    """REQ-003-004: adding a new plugin must require ZERO Python edits.

    Builds a temporary marketplace.json + marketplace-counters.yaml + a
    fake source tree, then runs validate() pointed at them. No code in
    build/scripts/ is touched, proving the mapping is config-only.
    """

    def test_new_plugin_validates_without_python_changes(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "fake-plugin-src"
        src.mkdir()
        for name in ["one.md", "two.md", "three.md", "four.md"]:
            (src / name).write_text("agent body\n")
        (src / "README.md").write_text("docs\n")

        counters_yaml = tmp_path / "marketplace-counters.yaml"
        counters_yaml.write_text(
            'schemaVersion: "1.0"\n'
            "plugins:\n"
            "  fresh-plugin:\n"
            "    agent:\n"
            '      strategy: "md_agents"\n'
            '      sourceDir: "fake-plugin-src"\n'
            '      exclude: ["README.md"]\n'
        )

        marketplace = tmp_path / "marketplace.json"
        marketplace.write_text(
            json.dumps(
                {
                    "plugins": [
                        {
                            "name": "fresh-plugin",
                            "description": "4 agents in a brand-new plugin",
                            "source": "./fake-plugin-src",
                        }
                    ]
                }
            )
        )

        assert (
            validate(
                fix=False,
                counters_path=counters_yaml,
                marketplace_path=marketplace,
                repo_root=tmp_path,
            )
            == 0
        )

    def test_unknown_strategy_in_config_returns_error(
        self, tmp_path: Path
    ) -> None:
        counters_yaml = tmp_path / "marketplace-counters.yaml"
        counters_yaml.write_text(
            'schemaVersion: "1.0"\n'
            "plugins:\n"
            "  bad:\n"
            "    agent:\n"
            '      strategy: "no_such_strategy"\n'
            '      sourceDir: "."\n'
        )
        marketplace = tmp_path / "marketplace.json"
        marketplace.write_text(json.dumps({"plugins": []}))
        assert (
            validate(
                fix=False,
                counters_path=counters_yaml,
                marketplace_path=marketplace,
                repo_root=tmp_path,
            )
            == 2
        )

    def test_stale_count_in_new_plugin_detected(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "only.md").write_text("body\n")

        counters_yaml = tmp_path / "marketplace-counters.yaml"
        counters_yaml.write_text(
            'schemaVersion: "1.0"\n'
            "plugins:\n"
            "  test-plugin:\n"
            "    agent:\n"
            '      strategy: "md_agents"\n'
            '      sourceDir: "src"\n'
        )
        marketplace = tmp_path / "marketplace.json"
        marketplace.write_text(
            json.dumps(
                {
                    "plugins": [
                        {
                            "name": "test-plugin",
                            "description": "999 agents (stale)",
                        }
                    ]
                }
            )
        )
        assert (
            validate(
                fix=False,
                counters_path=counters_yaml,
                marketplace_path=marketplace,
                repo_root=tmp_path,
            )
            == 1
        )


class TestP1Fixes:
    """Coverage for P1 fixes from /test gates 1+2."""

    def test_missing_source_dir_yields_config_error_not_traceback(
        self, tmp_path: Path
    ) -> None:
        """Gate-1 F-001: misconfigured sourceDir → exit 2 (ConfigError)."""
        counters_yaml = tmp_path / "marketplace-counters.yaml"
        counters_yaml.write_text(
            'schemaVersion: "1.0"\n'
            "plugins:\n"
            "  bad:\n"
            "    agent:\n"
            '      strategy: "md_agents"\n'
            '      sourceDir: "does-not-exist"\n'
        )
        marketplace = tmp_path / "marketplace.json"
        marketplace.write_text(json.dumps({"plugins": []}))
        assert (
            validate(
                fix=False,
                counters_path=counters_yaml,
                marketplace_path=marketplace,
                repo_root=tmp_path,
            )
            == 2
        )

    def test_walk_files_prunes_excluded_dirs(self, tmp_path: Path) -> None:
        """Counters must skip excluded dirs to prevent CI hangs."""
        from validate_marketplace_counts import _walk_files

        src = tmp_path / "src"
        src.mkdir()
        (src / "real.py").write_text("# real\n")
        node_modules = src / "node_modules" / "deep" / "more"
        node_modules.mkdir(parents=True)
        (node_modules / "vendored.py").write_text("# vendored\n")
        git_dir = src / ".git" / "objects"
        git_dir.mkdir(parents=True)
        (git_dir / "should-skip.py").write_text("# skip\n")

        assert _walk_files(src, ".py", set()) == 1
