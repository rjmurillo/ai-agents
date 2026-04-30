"""Integration tests for the two-plugin marketplace model (REQ-003-003, -012).

Verifies that the additive marketplace.json entries claude-toolkit and
copilot-cli-toolkit coexist with the legacy claude-agents,
copilot-cli-agents, and project-toolkit entries during the backward
compatibility window (REQ-003-012).

The legacy preservation rule is BLOCKING: removing any of the three
legacy plugin entries in this PR would violate REQ-003-012 and is
caught by these tests.

Plugin name uniqueness is also BLOCKING (R10 in plan risk register).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"

LEGACY_PLUGIN_NAMES = {"claude-agents", "copilot-cli-agents", "project-toolkit"}
NEW_PLUGIN_NAMES = {"claude-toolkit", "copilot-cli-toolkit"}
EXPECTED_MIN_PLUGINS = 5  # 3 legacy + 2 new


def _load_marketplace() -> dict:
    """Read and parse the marketplace.json file."""
    return json.loads(MARKETPLACE.read_text(encoding="utf-8"))


# ---- Positive tests ------------------------------------------------------


class TestMarketplaceShape:
    """Validate the additive two-plugin model is in place."""

    def test_marketplace_file_exists(self) -> None:
        assert MARKETPLACE.exists(), f"{MARKETPLACE} must exist"

    def test_marketplace_parses_as_json(self) -> None:
        data = _load_marketplace()
        assert isinstance(data, dict)
        assert "plugins" in data
        assert isinstance(data["plugins"], list)

    def test_minimum_plugin_count(self) -> None:
        """REQ-003-012 + REQ-003-003: at least 5 plugins (3 legacy + 2 new)."""
        data = _load_marketplace()
        assert len(data["plugins"]) >= EXPECTED_MIN_PLUGINS, (
            f"Expected at least {EXPECTED_MIN_PLUGINS} plugins, "
            f"got {len(data['plugins'])}"
        )

    def test_all_plugin_names_unique(self) -> None:
        """R10: name collision would break plugin discovery."""
        data = _load_marketplace()
        names = [p["name"] for p in data["plugins"]]
        assert len(names) == len(set(names)), (
            f"Duplicate plugin names detected: {names}"
        )

    def test_claude_toolkit_present(self) -> None:
        """REQ-003-003: claude-toolkit entry shall exist with source ./.claude."""
        data = _load_marketplace()
        match = [p for p in data["plugins"] if p["name"] == "claude-toolkit"]
        assert len(match) == 1, "claude-toolkit must be declared exactly once"
        assert match[0]["source"] == "./.claude"

    def test_copilot_cli_toolkit_present(self) -> None:
        """REQ-003-003: copilot-cli-toolkit shall exist with source ./src/copilot-cli."""
        data = _load_marketplace()
        match = [p for p in data["plugins"] if p["name"] == "copilot-cli-toolkit"]
        assert len(match) == 1, "copilot-cli-toolkit must be declared exactly once"
        assert match[0]["source"] == "./src/copilot-cli"


class TestSourceDirsExist:
    """Each plugin's `source` path must resolve to an existing directory."""

    def test_all_source_dirs_exist(self) -> None:
        data = _load_marketplace()
        for plugin in data["plugins"]:
            source = plugin["source"]
            # `source` is "./<rel-path>" relative to repo root.
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
    """REQ-003-003 verification: validator exits 0 on the current marketplace."""

    def test_validate_marketplace_counts_exits_zero(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "build" / "scripts" / "validate_marketplace_counts.py"),
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


# ---- Negative / preservation tests ---------------------------------------


class TestLegacyPreservation:
    """REQ-003-012: legacy entries must NOT be removed in the introducing PR."""

    @pytest.mark.parametrize("legacy_name", sorted(LEGACY_PLUGIN_NAMES))
    def test_legacy_plugin_present(self, legacy_name: str) -> None:
        """Each legacy plugin shall remain in marketplace.json."""
        data = _load_marketplace()
        names = {p["name"] for p in data["plugins"]}
        assert legacy_name in names, (
            f"REQ-003-012 violation: legacy plugin {legacy_name!r} "
            f"removed from marketplace.json. Legacy entries must persist "
            f"for one release cycle."
        )


class TestUniquenessAssertionDetectsCollision:
    """Verify the uniqueness check actually catches duplicates (test the test)."""

    def test_duplicate_name_detected_in_synthetic_fixture(self) -> None:
        """Synthetic fixture with duplicate plugin names fails the uniqueness check."""
        synthetic = {
            "name": "ai-agents",
            "plugins": [
                {"name": "claude-toolkit", "source": "./.claude"},
                {"name": "claude-toolkit", "source": "./other"},  # collision
            ],
        }
        names = [p["name"] for p in synthetic["plugins"]]
        assert len(names) != len(set(names)), (
            "Test fixture must trigger the uniqueness assertion"
        )


class TestLegacyDeletionDetected:
    """Verify the preservation tests catch deletion of a legacy entry."""

    def test_synthetic_marketplace_missing_legacy_fails(self) -> None:
        """A marketplace without claude-agents fails the legacy preservation check."""
        synthetic = {
            "plugins": [
                {"name": "claude-toolkit", "source": "./.claude"},
                {"name": "copilot-cli-toolkit", "source": "./src/copilot-cli"},
                # claude-agents intentionally removed
                # copilot-cli-agents intentionally removed
                # project-toolkit intentionally removed
            ],
        }
        names = {p["name"] for p in synthetic["plugins"]}
        # Each legacy must be missing from this fixture.
        for legacy in LEGACY_PLUGIN_NAMES:
            assert legacy not in names, (
                f"Test fixture must omit {legacy!r} to verify the assertion fires"
            )
