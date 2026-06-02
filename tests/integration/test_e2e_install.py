"""End-to-end install integration tests for project-toolkit in Copilot CLI (REQ-003-007).

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
     project-toolkit
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COPILOT_PLUGIN_SRC = REPO_ROOT / "src" / "copilot-cli"
COPILOT_PLUGIN_MANIFEST = COPILOT_PLUGIN_SRC / ".claude-plugin" / "plugin.json"
COPILOT_HOOKS_FILE = COPILOT_PLUGIN_SRC / "hooks" / "hooks.json"

# Copilot CLI hook event names. PascalCase event keys make Copilot CLI emit the
# VS Code-compatible snake_case payload (tool_name, tool_input) the shims expect;
# camelCase keys emit camelCase fields and break the shim contract (issue #2290).
VALID_COPILOT_EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
}

# Matches the script path that follows the plugin-root expansion in a hook
# command, e.g. ".../hooks/PreToolUse/invoke_x.py" -> "PreToolUse/invoke_x.py".
_HOOK_SCRIPT_PATH_RE = re.compile(r"/hooks/(?P<rel>[^\"']+\.py)")


def _resolve_case_sensitive(root: Path, relative: str) -> bool:
    """Resolve ``relative`` under ``root`` matching each path segment by exact case.

    ``Path.exists`` lies on case-insensitive filesystems (Windows, default macOS),
    so a PascalCase command path would falsely "resolve" against a lowercase
    directory. Walking the real directory entries makes the check case-sensitive
    on every host, catching the casing drift that broke Linux installs (#2290).
    """
    current = root
    for segment in Path(relative).parts:
        try:
            names = {entry.name for entry in current.iterdir()}
        except (FileNotFoundError, NotADirectoryError):
            return False
        if segment not in names:
            return False
        current = current / segment
    return current.is_file()


def _iter_hook_script_paths(hooks_data: dict) -> list[str]:
    """Yield every distinct /hooks/<rel>.py script path across bash and powershell."""
    paths: list[str] = []
    for entries in hooks_data.get("hooks", {}).values():
        for entry in entries:
            for shell in ("bash", "powershell"):
                command = entry.get(shell, "")
                for match in _HOOK_SCRIPT_PATH_RE.finditer(command):
                    paths.append(match.group("rel"))
    return paths


pytestmark = pytest.mark.integration


@pytest.fixture
def installed_plugin(tmp_path: Path) -> Path:
    """Copy src/copilot-cli/ into a fresh temp dir to simulate a plugin install.

    Returns the install root inside tmp_path.
    """
    install_root = tmp_path / "project-toolkit"
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

    def test_manifest_name_is_project_toolkit(
        self, installed_plugin: Path
    ) -> None:
        manifest = installed_plugin / ".claude-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data.get("name") == "project-toolkit"

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

    def test_hook_command_paths_resolve_case_sensitively(
        self, installed_plugin: Path
    ) -> None:
        """Every /hooks/<dir>/<script>.py path in hooks.json must resolve to a
        committed file matching by exact case (regression guard for #2290).

        hooks.json command paths are PascalCase (PreToolUse, ...). If the on-disk
        hook script directories drift to a different case, Copilot CLI on
        case-sensitive Linux cannot launch the script and every guard silently
        fails. A case-insensitive Path.exists() would not catch this; this walks
        real directory entries so it fails on any host before reaching Linux CI.
        """
        data = json.loads(
            (installed_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        script_paths = _iter_hook_script_paths(data)
        assert script_paths, "expected at least one hook script command path"
        unresolved = [
            rel
            for rel in script_paths
            if not _resolve_case_sensitive(installed_plugin / "hooks", rel)
        ]
        assert not unresolved, (
            "hooks.json references script paths that do not resolve "
            f"case-sensitively under hooks/: {sorted(set(unresolved))}"
        )


class TestInstalledArtifactReadability:
    """Sample agent and skill artifacts must be readable from the install."""

    def test_at_least_one_agent_file(self, installed_plugin: Path) -> None:
        agents = list(installed_plugin.glob("agents/*.agent.md"))
        assert agents, "Install must contain at least one .agent.md file"

    def test_sample_agent_readable(self, installed_plugin: Path) -> None:
        agents = sorted(installed_plugin.glob("agents/*.agent.md"))
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
        assert "project-toolkit" in list_result.stdout, (
            f"project-toolkit not registered after install:\n"
            f"{list_result.stdout}"
        )
