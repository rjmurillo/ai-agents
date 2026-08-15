"""Tests for plugin identity validation in resolve_pr_conflicts.py.

Extracted from test_resolve_lib_dir.py to stay under the 500-line taste limit.
Validates that a foreign plugin with importable RepoInfo is rejected when its
.claude-plugin/plugin.json has the wrong identity.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "merge-resolver"
    / "scripts"
    / "resolve_pr_conflicts.py"
)
_CORE_PACKAGE_NAME = "github_core"
_CORE_MODULE_FILE_NAME = "api.py"
_PLUGIN_IDENTITY_NAME = "project-toolkit"
_PLUGIN_ROOT_ENV_VARS = frozenset(
    {"COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "GITHUB_WORKSPACE"}
)


def _add_plugin_manifest(root: Path) -> None:
    """Add the plugin identity manifest to a fixture root."""
    manifest_dir = root / ".claude-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": _PLUGIN_IDENTITY_NAME}), encoding="utf-8"
    )


def _make_plugin_root(base: Path, name: str) -> Path:
    """Create a valid plugin root with importable github_core and correct identity."""
    root = base / name
    package = root / "lib" / _CORE_PACKAGE_NAME
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / _CORE_MODULE_FILE_NAME).write_text(
        "class RepoInfo:\n    pass\n", encoding="utf-8"
    )
    _add_plugin_manifest(root)
    return root


def _make_impostor_plugin_root(base: Path, name: str) -> Path:
    """Create a plugin root with importable RepoInfo but wrong identity."""
    root = base / name
    package = root / "lib" / _CORE_PACKAGE_NAME
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / _CORE_MODULE_FILE_NAME).write_text(
        "class RepoInfo:\n    pass\n", encoding="utf-8"
    )
    manifest_dir = root / ".claude-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "plugin.json").write_text(
        json.dumps({"name": "foreign-plugin"}), encoding="utf-8"
    )
    return root


def _clear_plugin_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every plugin-root variable from the test process environment."""
    for name in _PLUGIN_ROOT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


class TestPluginIdentity:
    """A foreign plugin with importable RepoInfo is rejected by identity check."""

    def test_impostor_rejected_valid_selected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An impostor with correct module but wrong identity is skipped."""
        _clear_plugin_env(monkeypatch)
        impostor = _make_impostor_plugin_root(tmp_path, "impostor")
        valid = _make_plugin_root(tmp_path, "valid-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(impostor))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(valid))

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "resolve_pr_conflicts_identity_test", _SCRIPT
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod._LIB_DIR == str(valid / "lib")

    def test_no_manifest_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A candidate with no plugin.json at all is rejected."""
        _clear_plugin_env(monkeypatch)
        root = tmp_path / "no-manifest"
        package = root / "lib" / _CORE_PACKAGE_NAME
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / _CORE_MODULE_FILE_NAME).write_text(
            "class RepoInfo:\n    pass\n", encoding="utf-8"
        )
        valid = _make_plugin_root(tmp_path, "valid-plugin")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(root))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(valid))

        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "resolve_pr_conflicts_no_manifest_test", _SCRIPT
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod._LIB_DIR == str(valid / "lib")
