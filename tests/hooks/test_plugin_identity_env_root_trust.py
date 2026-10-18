"""Environment-selected plugin roots must not borrow the twin manifest (#5793).

ADR-109 B6 deleted ``.claude/.claude-plugin/plugin.json``. Several readers then
learned to trust ``.claude/`` through its twin manifest at
``../src/claude/.claude-plugin/plugin.json``. A root named by an environment
variable is attacker-influenceable, and so is the tree under it, forged twin
included. These tests pin the classification of every reader:

* self-relative root (computed from ``__file__``): the twin is trusted;
* environment-derived root: the manifest must sit at the candidate itself, or
  the candidate must be the self-relative root;
* project-side root (``<project>/.claude``, repository content): the twin is
  trusted, because that is how the self-hosting repository is recognized.

Readers with no environment input (``paths._plugin_install_root``,
``prose_lint._plugin_install_root``, ``plugin_roots``) get a spoofed-variable
test that shows the variable changes nothing.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = REPO_ROOT / ".claude"
LIB_DIR = str(CLAUDE_DIR / "lib")
HOOKS_DIR = str(CLAUDE_DIR / "hooks")
SESSION_START_DIR = str(CLAUDE_DIR / "hooks" / "SessionStart")
for _search_path in (LIB_DIR, HOOKS_DIR, SESSION_START_DIR):
    if _search_path not in sys.path:
        sys.path.insert(0, _search_path)

import invoke_dispatch_claude as entry
import plugin_hook_drift_model as drift_model

from scripts.validation import (
    check_plugin_frontmatter_self_containment as frontmatter_gate,
)

PLUGIN_NAME = "project-toolkit"
SPOOF_ENV_VARS = ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT")


def _load_by_path(name: str, path: Path) -> ModuleType:
    """Load a module that is not importable as a package."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = _load_by_path("bootstrap_5793", CLAUDE_DIR / "hooks" / "PreToolUse" / "_bootstrap.py")
paths_mod = _load_by_path("paths_5793", CLAUDE_DIR / "lib" / "paths.py")
prose_lint = _load_by_path(
    "prose_lint_5793", CLAUDE_DIR / "skills" / "prose-self-check" / "scripts" / "prose_lint.py"
)


def _write_manifest(path: Path, name: object = PLUGIN_NAME) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"name": name}), encoding="utf-8")


def _forged_twin_tree(base: Path) -> Path:
    """A ``.claude`` root with hooks and lib dirs, no own manifest, a forged twin.

    This is the shape an attacker builds: a plain manifest at the root would
    pass every reader anyway, so the twin is the only thing the fix removes.
    """
    claude = base / ".claude"
    (claude / "lib").mkdir(parents=True)
    (claude / "hooks" / "PreToolUse").mkdir(parents=True)
    _write_manifest(base / "src" / "claude" / ".claude-plugin" / "plugin.json")
    return claude


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No inherited plugin or project variables; sys.path restored afterwards."""
    for var in (*SPOOF_ENV_VARS, "CLAUDE_PROJECT_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    return monkeypatch


class TestEnsurePluginPaths:
    """``_bootstrap.ensure_plugin_paths``: env root versus walk-up."""

    def test_env_root_with_only_a_forged_twin_is_rejected(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        forged = _forged_twin_tree(tmp_path)
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(forged))
        before = list(sys.path)
        with pytest.raises(bootstrap.PluginInfrastructureError, match="marker missing"):
            bootstrap.ensure_plugin_paths()
        assert sys.path == before

    def test_env_root_with_its_own_manifest_is_accepted(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        forged = _forged_twin_tree(tmp_path)
        _write_manifest(forged / ".claude-plugin" / "plugin.json")
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(forged))
        bootstrap.ensure_plugin_paths()
        assert str(forged / "lib") in sys.path

    def test_env_root_equal_to_the_self_relative_root_keeps_the_twin(
        self, clean_env: pytest.MonkeyPatch
    ) -> None:
        # Claude Code sets CLAUDE_PLUGIN_ROOT=.claude for this repository's
        # project plugin. That root has no manifest of its own after B6.
        assert not (CLAUDE_DIR / ".claude-plugin" / "plugin.json").exists()
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(CLAUDE_DIR))
        bootstrap.ensure_plugin_paths()
        assert str(CLAUDE_DIR / "lib") in sys.path

    def test_env_root_without_any_marker_is_rejected(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        bare = tmp_path / "plugin"
        (bare / "lib").mkdir(parents=True)
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(bare))
        with pytest.raises(bootstrap.PluginInfrastructureError, match="marker missing"):
            bootstrap.ensure_plugin_paths()

    def test_missing_env_root_is_rejected(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "absent"))
        with pytest.raises(bootstrap.PluginInfrastructureError, match="not a directory"):
            bootstrap.ensure_plugin_paths()

    def test_walk_up_still_trusts_the_twin(self, clean_env: pytest.MonkeyPatch) -> None:
        bootstrap.ensure_plugin_paths()
        assert str(CLAUDE_DIR / "lib") in sys.path

    def test_self_relative_root_is_this_checkouts_claude_dir(self) -> None:
        assert bootstrap._self_relative_root() == CLAUDE_DIR

    def test_twin_marker_requires_a_root_named_dot_claude(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path / "src" / "claude" / ".claude-plugin" / "plugin.json")
        other = tmp_path / "plugin"
        other.mkdir()
        assert bootstrap._has_own_or_twin_marker(other) is False
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        assert bootstrap._has_own_or_twin_marker(dot_claude) is True
        assert bootstrap._has_own_marker(dot_claude) is False


class TestProjectSelfHostsPlugin:
    """``invoke_dispatch_claude._project_self_hosts_plugin``."""

    def test_spoofed_env_root_cannot_trigger_the_self_host_bail(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # The project is this real repository (identity via its twin). A
        # forged env root claiming the same identity would make the dispatcher
        # skip every guard group if the twin were trusted for it.
        forged = _forged_twin_tree(tmp_path)
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(forged))
        clean_env.setenv("CLAUDE_PROJECT_DIR", str(REPO_ROOT))
        assert entry._project_self_hosts_plugin() is False

    def test_env_root_with_its_own_manifest_matches_the_project(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        installed = tmp_path / "installed"
        _write_manifest(installed / ".claude-plugin" / "plugin.json")
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(installed))
        clean_env.setenv("CLAUDE_PROJECT_DIR", str(REPO_ROOT))
        assert entry._project_self_hosts_plugin() is True

    def test_self_relative_env_root_matches_the_project(
        self, clean_env: pytest.MonkeyPatch
    ) -> None:
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(CLAUDE_DIR))
        clean_env.setenv("CLAUDE_PROJECT_DIR", str(REPO_ROOT))
        assert entry._project_self_hosts_plugin() is True

    def test_project_side_candidate_keeps_the_twin(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        installed = tmp_path / "installed"
        _write_manifest(installed / ".claude-plugin" / "plugin.json")
        project = tmp_path / "project"
        _forged_twin_tree(project)
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(installed))
        clean_env.setenv("CLAUDE_PROJECT_DIR", str(project))
        assert entry._project_self_hosts_plugin() is True

    def test_different_project_identity_does_not_bail(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        installed = tmp_path / "installed"
        _write_manifest(installed / ".claude-plugin" / "plugin.json")
        project = tmp_path / "project"
        _write_manifest(project / ".claude" / ".claude-plugin" / "plugin.json", "other-plugin")
        clean_env.setenv("CLAUDE_PLUGIN_ROOT", str(installed))
        clean_env.setenv("CLAUDE_PROJECT_DIR", str(project))
        assert entry._project_self_hosts_plugin() is False

    def test_unset_env_root_does_not_bail(self, clean_env: pytest.MonkeyPatch) -> None:
        assert entry._project_self_hosts_plugin() is False

    def test_plugin_name_reads_the_twin_only_when_trusted(self, tmp_path: Path) -> None:
        forged = _forged_twin_tree(tmp_path)
        assert entry._plugin_name(forged, trust_twin=False) is None
        assert entry._plugin_name(forged, trust_twin=True) == PLUGIN_NAME

    def test_plugin_name_prefers_the_roots_own_manifest(self, tmp_path: Path) -> None:
        forged = _forged_twin_tree(tmp_path)
        _write_manifest(forged / ".claude-plugin" / "plugin.json", "own-name")
        assert entry._plugin_name(forged, trust_twin=True) == "own-name"
        assert entry._plugin_name(forged, trust_twin=False) == "own-name"

    @pytest.mark.parametrize("payload", ["[]", "null", '{"name": ""}', '{"name": 7}', "not json"])
    def test_plugin_name_rejects_malformed_manifests(self, tmp_path: Path, payload: str) -> None:
        manifest = tmp_path / "root" / ".claude-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(payload, encoding="utf-8")
        assert entry._plugin_name(tmp_path / "root", trust_twin=True) is None

    def test_is_own_plugin_root_compares_by_location(self, tmp_path: Path) -> None:
        assert entry._is_own_plugin_root(CLAUDE_DIR) is True
        assert entry._is_own_plugin_root(tmp_path) is False


class TestReadPluginIdentity:
    """``plugin_hook_drift_model.read_plugin_identity`` and the install scan."""

    def test_default_ignores_the_twin(self, tmp_path: Path) -> None:
        forged = _forged_twin_tree(tmp_path)
        assert drift_model.read_plugin_identity(forged) == (None, False)

    def test_trusted_twin_is_read(self, tmp_path: Path) -> None:
        forged = _forged_twin_tree(tmp_path)
        assert drift_model.read_plugin_identity(forged, trust_twin=True) == (PLUGIN_NAME, False)

    def test_twin_is_ignored_for_a_root_not_named_dot_claude(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path / "src" / "claude" / ".claude-plugin" / "plugin.json")
        other = tmp_path / "plugin"
        other.mkdir()
        assert drift_model.read_plugin_identity(other, trust_twin=True) == (None, False)

    def test_own_manifest_is_read_without_the_twin(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        _write_manifest(root / ".claude-plugin" / "plugin.json")
        assert drift_model.read_plugin_identity(root) == (PLUGIN_NAME, False)

    def test_read_plugin_name_ignores_the_twin(self, tmp_path: Path) -> None:
        forged = _forged_twin_tree(tmp_path)
        assert drift_model.read_plugin_name(forged) is None

    def test_install_scan_does_not_report_a_forged_dot_claude_root(self, tmp_path: Path) -> None:
        import invoke_plugin_hook_drift_check as drift

        _forged_twin_tree(tmp_path)
        found = drift.find_installed_roots(tmp_path, PLUGIN_NAME)
        assert tmp_path / ".claude" not in found
        # The twin tree carries a real manifest, so it is a legitimate hit.
        assert tmp_path / "src" / "claude" in found


class TestReadersWithoutEnvironmentInput:
    """Self-relative readers ignore a spoofed root variable."""

    @pytest.mark.parametrize("var", SPOOF_ENV_VARS)
    def test_paths_install_root_ignores_spoofed_env(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path, var: str
    ) -> None:
        expected = paths_mod._plugin_install_root()
        clean_env.setenv(var, str(_forged_twin_tree(tmp_path)))
        assert paths_mod._plugin_install_root() == expected == CLAUDE_DIR

    @pytest.mark.parametrize("var", SPOOF_ENV_VARS)
    def test_prose_lint_install_root_ignores_spoofed_env(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path, var: str
    ) -> None:
        expected = prose_lint._plugin_install_root()
        clean_env.setenv(var, str(_forged_twin_tree(tmp_path)))
        # `.claude/skills/<name>` is a symlink into src/claude/skills (ADR-119), so the
        # walk up from the resolved script file lands on the plugin tree, which carries
        # the plugin manifest. The spoofed variable must not move it.
        assert prose_lint._plugin_install_root() == expected == REPO_ROOT / "src" / "claude"

    @pytest.mark.parametrize("var", SPOOF_ENV_VARS)
    def test_frontmatter_gate_plugin_roots_ignore_spoofed_env(
        self, clean_env: pytest.MonkeyPatch, tmp_path: Path, var: str
    ) -> None:
        expected = frontmatter_gate.plugin_roots(REPO_ROOT)
        clean_env.setenv(var, str(_forged_twin_tree(tmp_path)))
        assert frontmatter_gate.plugin_roots(REPO_ROOT) == expected
        assert ".claude" in expected

    def test_frontmatter_gate_adds_dot_claude_only_when_present(self, tmp_path: Path) -> None:
        manifest = {"plugins": [{"source": "./src/claude"}]}
        (tmp_path / ".claude-plugin").mkdir()
        (tmp_path / ".claude-plugin" / "marketplace.json").write_text(json.dumps(manifest))
        (tmp_path / ".github" / "plugin").mkdir(parents=True)
        (tmp_path / ".github" / "plugin" / "marketplace.json").write_text(json.dumps(manifest))
        (tmp_path / "src" / "claude").mkdir(parents=True)
        assert frontmatter_gate.plugin_roots(tmp_path) == ("src/claude",)
        (tmp_path / ".claude").mkdir()
        assert frontmatter_gate.plugin_roots(tmp_path) == ("src/claude", ".claude")
