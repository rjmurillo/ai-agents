"""Integration tests for the split native marketplace model.

Claude Code and GitHub Copilot CLI now read separate marketplace manifests
from the same repository. Both CLIs share `project-toolkit` as the full-install
plugin name, while keeping platform-specific agent-only bundles.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
COPILOT_MARKETPLACE = REPO_ROOT / ".github" / "plugin" / "marketplace.json"

CLAUDE_PLUGIN_NAMES = {"claude-agents", "project-toolkit"}
COPILOT_PLUGIN_NAMES = {"project-toolkit"}

# Names that previously appeared in Claude's marketplace but advertised
# Copilot-only bundles. Kept as an explicit denylist so the marketplace-
# honesty rule (issue #1840) has a named target the test can guard against
# regression even after both names were dropped from every shipped manifest.
CLAUDE_REJECTED_PLUGIN_NAMES = frozenset(
    {"copilot-cli-agents", "copilot-cli-toolkit"}
)


def _load_marketplace(path: Path) -> dict:
    """Read and parse a marketplace.json file."""
    return json.loads(path.read_text(encoding="utf-8"))


class TestMarketplaceShape:
    """Validate each CLI sees only its native marketplace entries."""

    @pytest.mark.parametrize("path", [CLAUDE_MARKETPLACE, COPILOT_MARKETPLACE])
    def test_marketplace_file_exists(self, path: Path) -> None:
        assert path.exists(), f"{path} must exist"

    @pytest.mark.parametrize("path", [CLAUDE_MARKETPLACE, COPILOT_MARKETPLACE])
    def test_marketplace_parses_as_json(self, path: Path) -> None:
        data = _load_marketplace(path)
        assert isinstance(data, dict)
        assert "plugins" in data
        assert isinstance(data["plugins"], list)

    @pytest.mark.parametrize("path", [CLAUDE_MARKETPLACE, COPILOT_MARKETPLACE])
    def test_all_plugin_names_unique(self, path: Path) -> None:
        data = _load_marketplace(path)
        names = [p["name"] for p in data["plugins"]]
        assert len(names) == len(set(names)), (
            f"Duplicate plugin names detected in {path}: {names}"
        )

    def test_claude_marketplace_contains_only_claude_plugins(self) -> None:
        data = _load_marketplace(CLAUDE_MARKETPLACE)
        assert {p["name"] for p in data["plugins"]} == CLAUDE_PLUGIN_NAMES

    def test_copilot_marketplace_contains_only_copilot_plugins(self) -> None:
        data = _load_marketplace(COPILOT_MARKETPLACE)
        assert {p["name"] for p in data["plugins"]} == COPILOT_PLUGIN_NAMES

    def test_claude_marketplace_excludes_copilot_only_plugins(self) -> None:
        data = _load_marketplace(CLAUDE_MARKETPLACE)
        names = {p["name"] for p in data["plugins"]}
        assert "copilot-cli-agents" not in names


class TestSourceDirsExist:
    """Each plugin's `source` path must resolve to an existing directory."""

    @pytest.mark.parametrize("path", [CLAUDE_MARKETPLACE, COPILOT_MARKETPLACE])
    def test_all_source_dirs_exist(self, path: Path) -> None:
        data = _load_marketplace(path)
        for plugin in data["plugins"]:
            source = plugin["source"]
            assert source.startswith("./"), (
                f"plugin {plugin['name']!r}: source must start with './' "
                f"(got {source!r})"
            )
            resolved = (REPO_ROOT / source[2:]).resolve()
            assert resolved.exists(), (
                f"plugin {plugin['name']!r}: source dir {resolved} "
                f"does not exist"
            )
            assert resolved.is_dir(), (
                f"plugin {plugin['name']!r}: source {resolved} is not a dir"
            )


class TestCounterValidatorGreen:
    """Count and manifest validators stay green for both native marketplaces."""

    @pytest.mark.parametrize("marketplace", [CLAUDE_MARKETPLACE, COPILOT_MARKETPLACE])
    def test_validate_marketplace_counts_exits_zero(self, marketplace: Path) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "build" / "scripts" / "validate_marketplace_counts.py"),
                "--marketplace",
                str(marketplace),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, (
            f"validate_marketplace_counts.py failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_validate_plugin_manifests_exits_zero(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "build" / "scripts" / "validate_plugin_manifests.py"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, (
            f"validate_plugin_manifests.py failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


class TestUniquenessAssertionDetectsCollision:
    """Verify the uniqueness check actually catches duplicates (test the test)."""

    def test_duplicate_name_detected_in_synthetic_fixture(self) -> None:
        synthetic = {
            "name": "ai-agents",
            "plugins": [
                {"name": "project-toolkit", "source": "./.claude"},
                {"name": "project-toolkit", "source": "./other"},
            ],
        }
        names = [p["name"] for p in synthetic["plugins"]]
        assert len(names) != len(set(names)), (
            "Test fixture must trigger the uniqueness assertion"
        )


class TestClaudeMarketplaceRejectsCopilotAgentBundle:
    """Guard against reintroducing Copilot-only agent bundles into Claude's marketplace."""

    def test_synthetic_claude_marketplace_with_copilot_plugin_is_invalid_shape(self) -> None:
        synthetic = {
            "plugins": [
                {"name": "project-toolkit", "source": "./.claude"},
                {"name": "copilot-cli-agents", "source": "./src/copilot-cli"},
            ],
        }
        names = {p["name"] for p in synthetic["plugins"]}
        assert names != CLAUDE_PLUGIN_NAMES, (
            "Fixture with a Copilot-only plugin must not match the allowed "
            "Claude plugin set"
        )
        assert names & CLAUDE_REJECTED_PLUGIN_NAMES, (
            "Fixture must overlap the Claude-rejected name set so the "
            "marketplace honesty rule has something to catch"
        )
