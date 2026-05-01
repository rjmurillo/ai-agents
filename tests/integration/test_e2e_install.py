"""End-to-end install integration tests for copilot-cli-toolkit (REQ-003-007).

Heavy integration tests that simulate installing src/copilot-cli/ as a
Copilot CLI plugin into a temp directory and verify the resulting
artifact tree is well-formed.

Marked with @pytest.mark.integration. The Copilot-CLI-binary-dependent
test additionally skips when `copilot` is not on PATH (covers contributors
without Copilot CLI installed; runs in nightly CI when present).

Verification scope (per task M6-T5):
  1. plugin.json parses and preserves only metadata required by marketplace install
  2. hooks.json has version: 1 wrapper + valid event keys
  3. sample agent file readable
  4. sample skill SKILL.md readable
  5. (conditional) copilot plugin install + copilot plugin list shows
     copilot-cli-toolkit
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COPILOT_PLUGIN_SRC = REPO_ROOT / "src" / "copilot-cli"
COPILOT_PLUGIN_MANIFEST = COPILOT_PLUGIN_SRC / ".claude-plugin" / "plugin.json"
COPILOT_HOOKS_FILE = COPILOT_PLUGIN_SRC / "hooks" / "hooks.json"

# Copilot CLI hook event names (camelCase). Distinct from Claude (PascalCase).
VALID_COPILOT_EVENTS = {
    "preToolUse",
    "postToolUse",
    "sessionStart",
    "sessionEnd",
    "userPromptSubmitted",
}


pytestmark = pytest.mark.integration


@pytest.fixture
def installed_plugin(tmp_path: Path) -> Path:
    """Copy src/copilot-cli/ into a fresh temp dir to simulate a plugin install.

    Returns the install root inside tmp_path.
    """
    install_root = tmp_path / "copilot-cli-toolkit"
    shutil.copytree(COPILOT_PLUGIN_SRC, install_root)
    return install_root


# ---- Structural verification (always runs in integration suite) ----------


class TestInstalledManifest:
    """plugin.json is the canonical entry point for the install."""

    def test_manifest_exists(self, installed_plugin: Path) -> None:
        manifest = installed_plugin / ".claude-plugin" / "plugin.json"
        assert manifest.exists(), f"{manifest} missing post-install"

    def test_manifest_parses(self, installed_plugin: Path) -> None:
        manifest = installed_plugin / ".claude-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_manifest_name_is_copilot_cli_toolkit(
        self, installed_plugin: Path
    ) -> None:
        manifest = installed_plugin / ".claude-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data.get("name") == "copilot-cli-toolkit"

    def test_manifest_omits_runtime_rejected_discovery_keys(
        self, installed_plugin: Path
    ) -> None:
        """Claude marketplace manifests rely on auto-discovery, not explicit keys."""
        manifest = installed_plugin / ".claude-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for field in ("agents", "skills", "commands", "hooks"):
            assert field not in data, (
                f"plugin.json should omit '{field}' because Claude Code rejects it "
                "for marketplace manifests"
            )


class TestInstalledHooks:
    """hooks/hooks.json must satisfy REQ-003-007 wrapper + event constraints."""

    def test_hooks_file_exists(self, installed_plugin: Path) -> None:
        assert (installed_plugin / "hooks" / "hooks.json").exists()

    def test_hooks_has_version_1_wrapper(self, installed_plugin: Path) -> None:
        """REQ-003-007: top-level {"version": 1, "hooks": {...}}."""
        data = json.loads(
            (installed_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        assert data.get("version") == 1, (
            f"hooks.json must have version: 1 (got {data.get('version')!r})"
        )

    def test_hooks_event_keys_are_valid(self, installed_plugin: Path) -> None:
        data = json.loads(
            (installed_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        events = data.get("hooks", {})
        assert isinstance(events, dict), "hooks.hooks must be an object"
        unknown = set(events.keys()) - VALID_COPILOT_EVENTS
        assert not unknown, (
            f"Unknown Copilot CLI hook events: {unknown}. "
            f"Valid: {sorted(VALID_COPILOT_EVENTS)}"
        )

    def test_hooks_event_entries_are_lists(self, installed_plugin: Path) -> None:
        """Each event maps to a list of hook entry objects."""
        data = json.loads(
            (installed_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        for event, entries in data.get("hooks", {}).items():
            assert isinstance(entries, list), (
                f"hooks.{event} must be a list, got {type(entries).__name__}"
            )
            assert entries, f"hooks.{event} must not be empty"


class TestInstalledArtifactReadability:
    """Sample agent and skill artifacts must be readable from the install."""

    def test_at_least_one_agent_file(self, installed_plugin: Path) -> None:
        agents = list(installed_plugin.glob("*.agent.md"))
        assert agents, "Install must contain at least one .agent.md file"

    def test_sample_agent_readable(self, installed_plugin: Path) -> None:
        agents = sorted(installed_plugin.glob("*.agent.md"))
        sample = agents[0]
        text = sample.read_text(encoding="utf-8")
        assert text.strip(), f"{sample.name} is empty"

    def test_at_least_one_skill_dir(self, installed_plugin: Path) -> None:
        skills_dir = installed_plugin / "skills"
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        assert skill_dirs, "Install must contain at least one skill directory"

    def test_sample_skill_md_readable(self, installed_plugin: Path) -> None:
        skills_dir = installed_plugin / "skills"
        # Find first skill with a SKILL.md file (canonical contract).
        for skill in sorted(skills_dir.iterdir()):
            if not skill.is_dir():
                continue
            skill_md = skill / "SKILL.md"
            if skill_md.exists():
                text = skill_md.read_text(encoding="utf-8")
                assert text.strip(), f"{skill_md} is empty"
                return
        pytest.fail("No skill subdir contained a readable SKILL.md")


# ---- Conditional binary test (skips when Copilot CLI not installed) ------


class TestCopilotBinaryInstall:
    """Smoke test: invoke `copilot` to install the plugin and list it.

    Skips when `copilot` is not on PATH so contributor laptops without
    the binary do not block CI.
    """

    @pytest.fixture
    def copilot_binary(self) -> str:
        binary = shutil.which("copilot")
        if binary is None:
            pytest.skip("copilot CLI not on PATH; nightly-only smoke test")
        return binary

    def test_copilot_plugin_install_succeeds(
        self, copilot_binary: str, installed_plugin: Path, tmp_path: Path
    ) -> None:
        """`copilot plugin install <local-dir>` exits 0 and registers the plugin."""
        install_result = subprocess.run(
            [copilot_binary, "plugin", "install", str(installed_plugin)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert install_result.returncode == 0, (
            f"copilot plugin install failed:\n"
            f"stdout: {install_result.stdout}\n"
            f"stderr: {install_result.stderr}"
        )

        list_result = subprocess.run(
            [copilot_binary, "plugin", "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert list_result.returncode == 0
        assert "copilot-cli-toolkit" in list_result.stdout, (
            f"copilot-cli-toolkit not registered after install:\n"
            f"{list_result.stdout}"
        )
