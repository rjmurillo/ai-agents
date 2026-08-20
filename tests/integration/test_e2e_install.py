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

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COPILOT_PLUGIN_SRC = REPO_ROOT / "src" / "copilot-cli"
COPILOT_PLUGIN_MANIFEST = COPILOT_PLUGIN_SRC / ".claude-plugin" / "plugin.json"
COPILOT_HOOKS_FILE = COPILOT_PLUGIN_SRC / "hooks" / "hooks.json"

# Real Copilot CLI home. The binary-dependent smoke test below shells out to
# `copilot plugin install`, which mutates this global config; teardown must
# restore it (see _remove_direct_shadow).
COPILOT_HOME = Path.home() / ".copilot"
PLUGIN_NAME = "project-toolkit"

# Environment variables Copilot CLI reads to locate a package cache. Its
# bootstrap scans these *before* COPILOT_HOME, so leaving them pointed at the
# real user profile lets an isolated run load a cached package from outside the
# sandbox, and lets it write there. HOME and USERPROFILE alone are not enough.
_COPILOT_CACHE_VARS = ("LOCALAPPDATA", "XDG_CACHE_HOME", "COPILOT_CACHE_HOME")
_COPILOT_CREDENTIAL_VARS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def isolated_copilot_env(home: Path) -> dict[str, str]:
    """Environment that confines Copilot CLI to ``home``.

    ``USERPROFILE`` is not optional. ``Path.home()`` consults it first on
    Windows, so a HOME-only env leaked a ``_direct`` shadow into the
    contributor's real ~/.copilot for nine days (#3324). The POSIX-only test
    leg is why the POSIX-only fix looked complete.

    Auto-update is disabled so a background version fetch cannot write outside
    the sandbox or make the run depend on network state.
    """
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "COPILOT_HOME": str(home / ".copilot"),
        "COPILOT_AUTO_UPDATE": "false",
    }
    for name in _COPILOT_CACHE_VARS:
        env[name] = str(home / "cache" / name.lower())
    for name in list(env):
        if name.upper() in _COPILOT_CREDENTIAL_VARS:
            env.pop(name)
    return env


# Copilot CLI hook event names. PascalCase event keys make Copilot CLI emit the
# VS Code-compatible snake_case payload (tool_name, tool_input) the shims expect;
# camelCase keys emit camelCase fields and break the shim contract (issue #2290).
VALID_COPILOT_EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "SubagentStop",
    "PermissionRequest",
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


def _iter_hook_script_paths(hooks_data: dict[str, Any]) -> list[str]:
    """Yield every distinct /hooks/<rel>.py script path across bash and powershell."""
    paths: list[str] = []
    for entries in hooks_data.get("hooks", {}).values():
        for entry in entries:
            for shell in ("bash", "powershell"):
                command = entry.get(shell, "")
                for match in _HOOK_SCRIPT_PATH_RE.finditer(command):
                    paths.append(match.group("rel"))
    return paths


pytestmark = [pytest.mark.integration, pytest.mark.windows_path]


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

    def test_manifest_name_is_project_toolkit(self, installed_plugin: Path) -> None:
        manifest = installed_plugin / ".claude-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert data.get("name") == "project-toolkit"

    def test_manifest_omits_runtime_rejected_discovery_keys(self, installed_plugin: Path) -> None:
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
        data = json.loads((installed_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        assert data.get("version") == 1, (
            f"hooks.json must have version: 1 (got {data.get('version')!r})"
        )

    def test_hooks_event_keys_are_valid(self, installed_plugin: Path) -> None:
        data = json.loads((installed_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        events = data.get("hooks", {})
        assert isinstance(events, dict), "hooks.hooks must be an object"
        unknown = set(events.keys()) - VALID_COPILOT_EVENTS
        assert not unknown, (
            f"Unknown Copilot CLI hook events: {unknown}. Valid: {sorted(VALID_COPILOT_EVENTS)}"
        )

    def test_hooks_event_entries_are_lists(self, installed_plugin: Path) -> None:
        """Each event maps to a list of hook entry objects."""
        data = json.loads((installed_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        for event, entries in data.get("hooks", {}).items():
            assert isinstance(entries, list), (
                f"hooks.{event} must be a list, got {type(entries).__name__}"
            )
            assert entries, f"hooks.{event} must not be empty"

    def test_hook_command_paths_resolve_case_sensitively(self, installed_plugin: Path) -> None:
        """Every /hooks/<dir>/<script>.py path in hooks.json must resolve to a
        committed file matching by exact case (regression guard for #2290).

        hooks.json command paths are PascalCase (PreToolUse, ...). If the on-disk
        hook script directories drift to a different case, Copilot CLI on
        case-sensitive Linux cannot launch the script and every guard silently
        fails. A case-insensitive Path.exists() would not catch this; this walks
        real directory entries so it fails on any host before reaching Linux CI.
        """
        data = json.loads((installed_plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        script_paths = _iter_hook_script_paths(data)
        # Zero registered hooks is a valid, deliberately-shipped state (ADR-097):
        # no script paths means nothing to resolve, not a missing-hook defect.
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


def _strip_jsonc(text: str) -> str:
    """Drop whole-line ``//`` comments from Copilot's managed config.json.

    Copilot writes a JSON-with-comments header ("This file is managed
    automatically."). No string value in this file begins a line with ``//``,
    so a line-oriented strip is sufficient and avoids a JSONC dependency.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


def _remove_direct_shadow(source_dir: Path, copilot_home: Path | None = None) -> None:
    """Undo the global side effect of ``copilot plugin install <source_dir>``.

    ``copilot plugin install <local-dir>`` registers a marketplace-less
    ("_direct") entry in the real ~/.copilot/config.json whose ``source.path``
    is ``source_dir``. Because ``source_dir`` lives under pytest's ``tmp_path``,
    pytest deletes it after the test, leaving an *enabled* duplicate hook
    install pointing at a dead path. That stale shadow doubles PreToolUse hook
    dispatch and, on version skew with the real marketplace install, can wedge
    every later Copilot session (all shell tools denied with "hook errored").

    Remove only the entry this test created so global state is restored. Match
    is scoped to a ``project-toolkit`` entry with no marketplace whose
    ``source.path`` resolves to ``source_dir`` (or under its tmp parent), so an
    unrelated real install is never touched.

    ``copilot_home`` is explicit rather than read from the module global so a
    caller can sweep more than one home. Teardown used to read the global, which
    the smoke test monkeypatched to the isolated dir; when isolation failed the
    cleanup looked in an empty directory and the real shadow survived (#3324).
    """
    home = COPILOT_HOME if copilot_home is None else copilot_home
    config_path = home / "config.json"
    if not config_path.is_file():
        return
    try:
        config = json.loads(_strip_jsonc(config_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return

    plugins = config.get("installedPlugins")
    if not isinstance(plugins, list):
        return

    source_resolved = source_dir.resolve()
    source_parent = source_resolved.parent

    def _is_created_shadow(entry: object) -> bool:
        if not isinstance(entry, dict):
            return False
        if entry.get("name") != PLUGIN_NAME or entry.get("marketplace"):
            return False
        source = entry.get("source")
        src_path = source.get("path") if isinstance(source, dict) else None
        if not src_path:
            return False
        candidate = Path(src_path)
        try:
            candidate_resolved = candidate.resolve()
        except (OSError, RuntimeError):
            candidate_resolved = candidate
        return (
            candidate.as_posix() == source_dir.as_posix()
            or candidate_resolved == source_resolved
            or source_parent in candidate_resolved.parents
        )

    remaining = [entry for entry in plugins if not _is_created_shadow(entry)]
    if len(remaining) == len(plugins):
        return  # This test did not register a shadow; leave the file untouched.

    config["installedPlugins"] = remaining
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    cache_dir = home / "installed-plugins" / "_direct" / PLUGIN_NAME
    if cache_dir.is_dir():
        shutil.rmtree(cache_dir, ignore_errors=True)


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
        self,
        copilot_binary: str,
        installed_plugin: Path,
        tmp_path: Path,
    ) -> None:
        """`copilot plugin install <local-dir>` exits 0 and registers the plugin.

        Runs against an isolated home so the install writes to a throwaway
        config under ``tmp_path`` instead of the real user config. Copilot CLI
        resolves its home from ``USERPROFILE`` on Windows and ``HOME`` on POSIX,
        so both are set: a HOME-only env leaked a ``_direct`` shadow into the
        contributor's real ~/.copilot on Windows for nine days (#3324).

        Isolation is asserted rather than assumed. A silent leak used to be
        invisible because teardown swept the isolated dir it was told to trust;
        now a leak is a red test, and teardown sweeps the real home too so it
        does not depend on the isolation it is meant to backstop.
        """
        isolated_home = tmp_path / "copilot-home"
        isolated_home.mkdir()
        isolated_copilot = isolated_home / ".copilot"
        env = isolated_copilot_env(isolated_home)
        try:
            install_result = subprocess.run(
                [copilot_binary, "plugin", "install", str(installed_plugin)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                env=env,
            )
            assert install_result.returncode == 0, (
                f"copilot plugin install failed:\n"
                f"stdout: {install_result.stdout}\n"
                f"stderr: {install_result.stderr}"
            )

            assert (isolated_copilot / "config.json").is_file(), (
                f"copilot did not write to the isolated home {isolated_copilot}. "
                f"The install went somewhere else, most likely the real "
                f"{Path.home() / '.copilot'}, which is the #3324 leak. Do not "
                f"weaken this assertion; find which env var the binary honors."
            )

            list_result = subprocess.run(
                [copilot_binary, "plugin", "list"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                env=env,
            )
            assert list_result.returncode == 0
            assert "project-toolkit" in list_result.stdout, (
                f"project-toolkit not registered after install:\n{list_result.stdout}"
            )
        finally:
            # Sweep both homes. The isolated one is where the install belongs;
            # the real one is the backstop for the case this test exists to
            # catch, where isolation silently did not take.
            for home in {isolated_copilot, COPILOT_HOME}:
                _remove_direct_shadow(installed_plugin, home)


@pytest.mark.integration
class TestDirectShadowCleanup:
    """Unit coverage for _remove_direct_shadow (runs without the copilot binary).

    Guards the regression where the binary smoke test left an enabled
    marketplace-less project-toolkit install in the real ~/.copilot/config.json
    pointing at a deleted pytest tmp dir, wedging later Copilot sessions.
    """

    @staticmethod
    def _write_config(copilot_home: Path, plugins: list[dict[str, Any]]) -> Path:
        copilot_home.mkdir(parents=True, exist_ok=True)
        config_path = copilot_home / "config.json"
        config_path.write_text(
            "// This file is managed automatically.\n" + json.dumps({"installedPlugins": plugins}),
            encoding="utf-8",
        )
        return config_path

    def test_removes_only_the_created_shadow(self, tmp_path: Path) -> None:
        copilot_home = tmp_path / ".copilot"
        source_dir = tmp_path / "src" / PLUGIN_NAME
        source_dir.mkdir(parents=True)
        real = {"name": PLUGIN_NAME, "marketplace": "ai-agents", "enabled": True}
        shadow = {
            "name": PLUGIN_NAME,
            "marketplace": "",
            "enabled": True,
            "source": {"source": "local", "path": str(source_dir)},
        }
        other = {"name": "caveman", "marketplace": "caveman", "enabled": True}
        config_path = self._write_config(copilot_home, [real, shadow, other])
        cache_dir = copilot_home / "installed-plugins" / "_direct" / PLUGIN_NAME
        cache_dir.mkdir(parents=True)
        _remove_direct_shadow(source_dir, copilot_home)

        result = json.loads(_strip_jsonc(config_path.read_text(encoding="utf-8")))
        surviving = [
            (entry["name"], entry.get("marketplace")) for entry in result["installedPlugins"]
        ]
        assert (PLUGIN_NAME, "") not in surviving
        assert (PLUGIN_NAME, "ai-agents") in surviving
        assert ("caveman", "caveman") in surviving
        assert not cache_dir.exists()

    def test_preserves_config_without_a_shadow(self, tmp_path: Path) -> None:
        copilot_home = tmp_path / ".copilot"
        source_dir = tmp_path / "src" / PLUGIN_NAME
        real = {"name": PLUGIN_NAME, "marketplace": "ai-agents", "enabled": True}
        config_path = self._write_config(copilot_home, [real])
        before = config_path.read_text(encoding="utf-8")
        _remove_direct_shadow(source_dir, copilot_home)

        assert config_path.read_text(encoding="utf-8") == before

    def test_leaves_unrelated_direct_install_untouched(self, tmp_path: Path) -> None:
        copilot_home = tmp_path / ".copilot"
        source_dir = tmp_path / "src" / PLUGIN_NAME
        unrelated = {
            "name": PLUGIN_NAME,
            "marketplace": "",
            "enabled": True,
            "source": {"source": "local", "path": "/some/other/checkout"},
        }
        config_path = self._write_config(copilot_home, [unrelated])
        _remove_direct_shadow(source_dir, copilot_home)

        result = json.loads(_strip_jsonc(config_path.read_text(encoding="utf-8")))
        assert result["installedPlugins"] == [unrelated]

    def test_noop_when_config_absent(self, tmp_path: Path) -> None:
        copilot_home = tmp_path / ".copilot"
        _remove_direct_shadow(tmp_path / "src" / PLUGIN_NAME, copilot_home)  # must not raise

        assert not (copilot_home / "config.json").exists()

    def test_survives_malformed_config(self, tmp_path: Path) -> None:
        copilot_home = tmp_path / ".copilot"
        copilot_home.mkdir(parents=True)
        config_path = copilot_home / "config.json"
        config_path.write_text("{ not valid json", encoding="utf-8")
        _remove_direct_shadow(tmp_path / "src" / PLUGIN_NAME, copilot_home)  # must not raise

        assert config_path.read_text(encoding="utf-8") == "{ not valid json"

    def test_sweeps_the_home_it_is_given_not_the_module_global(self, tmp_path: Path) -> None:
        # Teardown used to read the module global, which the smoke test
        # monkeypatched to the isolated dir. When isolation silently failed on
        # Windows, cleanup swept an empty directory and the real shadow
        # survived for nine days (#3324). The home is now explicit so the smoke
        # test can sweep the real one as a backstop.
        leaked_home = tmp_path / "real" / ".copilot"
        source_dir = tmp_path / "src" / PLUGIN_NAME
        source_dir.mkdir(parents=True)
        shadow = {
            "name": PLUGIN_NAME,
            "marketplace": "",
            "enabled": True,
            "source": {"source": "local", "path": str(source_dir)},
        }
        config_path = self._write_config(leaked_home, [shadow])

        _remove_direct_shadow(source_dir, leaked_home)

        result = json.loads(_strip_jsonc(config_path.read_text(encoding="utf-8")))
        assert result["installedPlugins"] == []

    def test_defaults_to_the_module_global_when_no_home_is_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The parameter is optional so existing callers keep working. Pin that
        # the default still resolves through COPILOT_HOME.
        copilot_home = tmp_path / ".copilot"
        source_dir = tmp_path / "src" / PLUGIN_NAME
        source_dir.mkdir(parents=True)
        shadow = {
            "name": PLUGIN_NAME,
            "marketplace": "",
            "enabled": True,
            "source": {"source": "local", "path": str(source_dir)},
        }
        config_path = self._write_config(copilot_home, [shadow])
        monkeypatch.setattr(f"{__name__}.COPILOT_HOME", copilot_home)

        _remove_direct_shadow(source_dir)

        result = json.loads(_strip_jsonc(config_path.read_text(encoding="utf-8")))
        assert result["installedPlugins"] == []

    def test_sweeping_two_homes_removes_both_shadows(self, tmp_path: Path) -> None:
        # The smoke test sweeps the isolated home and the real one. A leak
        # lands in exactly one of them and the caller does not know which, so
        # both must be swept unconditionally without the sweep of an untouched
        # home raising.
        source_dir = tmp_path / "src" / PLUGIN_NAME
        source_dir.mkdir(parents=True)
        shadow = {
            "name": PLUGIN_NAME,
            "marketplace": "",
            "enabled": True,
            "source": {"source": "local", "path": str(source_dir)},
        }
        homes = [tmp_path / "isolated" / ".copilot", tmp_path / "real" / ".copilot"]
        configs = [self._write_config(home, [shadow]) for home in homes]

        for home in homes:
            _remove_direct_shadow(source_dir, home)

        for config_path in configs:
            result = json.loads(_strip_jsonc(config_path.read_text(encoding="utf-8")))
            assert result["installedPlugins"] == []


class TestIsolatedCopilotEnv:
    """The env that confines the binary smoke test to a throwaway home.

    These run everywhere, including the Windows CI leg, without needing the
    `copilot` binary. That matters: the binary smoke test skips when the CLI is
    absent, so before this class the Windows leg proved nothing about the #3324
    fix. Deleting the USERPROFILE line left CI green.
    """

    def test_userprofile_points_at_the_isolated_home(self, tmp_path: Path) -> None:
        """Path.home() reads USERPROFILE first on Windows. This is the #3324 fix."""
        env = isolated_copilot_env(tmp_path)
        assert env["USERPROFILE"] == str(tmp_path)

    def test_home_points_at_the_isolated_home(self, tmp_path: Path) -> None:
        """POSIX reads HOME. Both must move together or one platform leaks."""
        env = isolated_copilot_env(tmp_path)
        assert env["HOME"] == str(tmp_path)

    def test_copilot_home_is_under_the_isolated_home(self, tmp_path: Path) -> None:
        env = isolated_copilot_env(tmp_path)
        assert Path(env["COPILOT_HOME"]) == tmp_path / ".copilot"

    @pytest.mark.parametrize("name", _COPILOT_CACHE_VARS)
    def test_package_cache_vars_are_redirected(self, tmp_path: Path, name: str) -> None:
        """Copilot scans these before COPILOT_HOME, so an unset one escapes."""
        env = isolated_copilot_env(tmp_path)
        assert Path(env[name]).is_relative_to(tmp_path), (
            f"{name} still points outside the sandbox, so a cached package "
            f"from the real user profile can be read or written"
        )

    def test_auto_update_is_disabled(self, tmp_path: Path) -> None:
        """A background update writes outside the sandbox and adds network flake."""
        assert isolated_copilot_env(tmp_path)["COPILOT_AUTO_UPDATE"] == "false"

    @pytest.mark.parametrize(
        "name",
        (
            *_COPILOT_CREDENTIAL_VARS,
            "copilot_github_token",
            "Gh_Token",
            "github_token",
        ),
    )
    def test_credentials_are_removed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        monkeypatch.setenv(name, "ambient-secret")
        assert name not in isolated_copilot_env(tmp_path)

    def test_no_isolated_var_is_passed_through_from_the_ambient_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guard the guard: catches a typo that silently reuses os.environ.

        Asserting the values sit under ``tmp_path`` cannot catch this, and
        every such assertion is already made above, one test per variable. The
        distinct question here is where the value came from, not what shape it
        has, so each variable gets a sentinel in the ambient environment first.
        A helper that reads ``os.environ[name]`` returns the sentinel; one that
        derives from ``tmp_path`` cannot.
        """
        names = ("HOME", "USERPROFILE", "COPILOT_HOME", *_COPILOT_CACHE_VARS)
        sentinels = {name: f"/sentinel/ambient/{name}" for name in names}
        for name, value in sentinels.items():
            monkeypatch.setenv(name, value)

        env = isolated_copilot_env(tmp_path)

        for name, value in sentinels.items():
            assert env[name] != value, (
                f"{name} was copied out of the ambient environment instead of "
                f"being derived from the sandbox root"
            )

    def test_unrelated_environment_is_preserved(self, tmp_path: Path) -> None:
        """PATH must survive, or the binary under test is not findable."""
        env = isolated_copilot_env(tmp_path)
        assert env.get("PATH") == os.environ.get("PATH")


class TestSubprocessDecoding:
    """Every captured subprocess in this module must pin its decoding.

    On Windows `subprocess.run(text=True, capture_output=True)` with no
    encoding defaults to cp1252, whose reader thread raises UnicodeDecodeError
    on the UTF-8 glyphs the CLI prints. The exception is swallowed and
    `result.stdout` comes back None, so assertions fail with a NoneType
    cascade that names nothing useful. Source inspection is the only way to
    guard this without a Windows runner and a real binary.
    """

    #: Stream kwargs that route a subprocess pipe back into this process.
    _PIPE_KWARGS = frozenset({"stdout", "stderr"})
    #: Boolean kwargs that put captured pipes into text mode when true.
    _TEXT_FLAGS = frozenset({"text", "universal_newlines"})
    #: Codec kwargs whose presence enables text-mode decoding.
    _TEXT_OPTIONS = frozenset({"encoding", "errors"})

    @classmethod
    def _captured_runs(cls, source: str | None = None) -> list[ast.Call]:
        """Return the ``subprocess.run`` calls that actually decode child output.

        Both halves of the predicate are load-bearing. A capture with no text
        mode returns bytes, never decodes, and must not be asked for an
        ``encoding``: adding one would silently flip it into text mode and
        change the value the caller gets back. Text mode with nothing captured
        writes straight to the terminal and decodes nothing in this process.
        Only the intersection can hit the Windows cp1252 reader-thread failure,
        so only the intersection is checked.

        ``source`` defaults to this module so the guard polices itself; tests
        pass a snippet to pin the predicate against shapes this file does not
        contain.
        """
        text = source if source is not None else Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "run"):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
                continue
            if any(keyword.arg is None for keyword in node.keywords):
                raise AssertionError(
                    f"subprocess.run at line {node.lineno} expands **kwargs; "
                    "the decoding guard cannot inspect bundled arguments"
                )
            kwargs = {kw.arg for kw in node.keywords}
            captures_output = any(
                keyword.arg == "capture_output"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
            captures_pipe = any(
                keyword.arg in cls._PIPE_KWARGS
                and isinstance(keyword.value, ast.Attribute)
                and keyword.value.attr == "PIPE"
                and isinstance(keyword.value.value, ast.Name)
                and keyword.value.value.id == "subprocess"
                for keyword in node.keywords
            )
            text_mode = bool(kwargs & cls._TEXT_OPTIONS) or any(
                keyword.arg in cls._TEXT_FLAGS
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
            if (captures_output or captures_pipe) and text_mode:
                calls.append(node)
        return calls

    def test_the_probe_finds_the_calls_it_claims_to_check(self) -> None:
        """Guard the guard: a rename would make the checks below vacuous."""
        assert len(self._captured_runs()) >= 2

    def test_byte_mode_capture_is_not_a_target(self) -> None:
        """A capture with no text mode returns bytes and must not be flagged.

        Demanding ``encoding=`` here would be worse than a false positive: the
        only way to satisfy it is to add the kwarg, which flips the call into
        text mode and changes what the caller receives.
        """
        assert self._captured_runs("subprocess.run(cmd, capture_output=True)") == []

    def test_text_mode_without_capture_is_not_a_target(self) -> None:
        """Nothing is piped back, so this process decodes nothing."""
        assert self._captured_runs("subprocess.run(cmd, text=True)") == []

    def test_captured_text_mode_is_a_target(self) -> None:
        """The intersection is the cp1252 failure mode, so it must be caught."""
        assert len(self._captured_runs("subprocess.run(cmd, capture_output=True, text=True)")) == 1

    @pytest.mark.parametrize("flag", ["text", "universal_newlines"])
    def test_explicit_false_text_flag_is_not_a_target(self, flag: str) -> None:
        assert self._captured_runs(f"subprocess.run(cmd, capture_output=True, {flag}=False)") == []

    def test_one_true_text_flag_overrides_the_other_false_flag(self) -> None:
        snippet = "subprocess.run(cmd, capture_output=True, text=False, universal_newlines=True)"
        assert len(self._captured_runs(snippet)) == 1

    def test_redirected_pipe_counts_as_capture(self) -> None:
        """stdout=PIPE decodes exactly like capture_output=True does."""
        snippet = "subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)"
        assert len(self._captured_runs(snippet)) == 1

    @pytest.mark.parametrize(
        "snippet",
        [
            "subprocess.run(cmd, capture_output=False, text=True)",
            "subprocess.run(cmd, stderr=subprocess.STDOUT, text=True)",
            "subprocess.run(cmd, stdout=subprocess.DEVNULL, text=True)",
        ],
    )
    def test_non_pipe_redirection_is_not_a_target(self, snippet: str) -> None:
        assert self._captured_runs(snippet) == []

    def test_bundled_kwargs_cannot_bypass_the_guard(self) -> None:
        with pytest.raises(AssertionError, match=r"expands \*\*kwargs"):
            self._captured_runs("subprocess.run(cmd, **kwargs)")

    def test_every_captured_run_pins_encoding_and_errors(self) -> None:
        for call in self._captured_runs():
            kwargs = {kw.arg for kw in call.keywords}
            assert "encoding" in kwargs, (
                f"subprocess.run at line {call.lineno} captures output without "
                f"encoding=; on Windows this decodes as cp1252 and returns None"
            )
            assert "errors" in kwargs, (
                f"subprocess.run at line {call.lineno} sets encoding but not "
                f"errors=; a stray byte then raises instead of degrading"
            )
