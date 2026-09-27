#!/usr/bin/env python3
"""Install-side manifest resolution tests for #5085's hook.

An installed copy is compared as its host would load it. Claude Code reads
plugin hooks only from ``hooks/hooks.json`` unless ``plugin.json`` declares a
``hooks`` field, so an install with neither enforces nothing. The shipped
plugin has been in that layout since #5784, and reading it as unreadable
flagged every current install at session start.

The negative controls pin what must stay an error: a broken manifest, a
declared hooks path, an unreadable ``plugin.json``, a Copilot install, and a
source checkout missing its own manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HOOKS_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart")
sys.path.insert(0, HOOKS_DIR)

import invoke_plugin_hook_drift_check as drift
import plugin_hook_drift_model as model

PLUGIN_NAME = "project-toolkit"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _plugin_root(root: Path, hooks: object) -> Path:
    """Lay out a plugin root: plugin manifest, plus hooks.json when given."""
    _write_json(root / ".claude-plugin" / "plugin.json", {"name": PLUGIN_NAME})
    if hooks is not None:
        _write_json(root / "hooks" / "hooks.json", {"hooks": hooks})
    return root


def _claude_hooks(command: str) -> dict:
    return {"PreToolUse": [{"matcher": "Task", "hooks": [{"type": "command", "command": command}]}]}


def test_install_registrations_reads_an_absent_claude_manifest_as_no_hooks(tmp_path) -> None:
    # Issue #5085: since #5784 the shipped plugin keeps its empty manifest at
    # the root, where Claude Code never reads it. Every current install lacks
    # hooks/hooks.json, and each one was reported unreadable at session start.
    install = _plugin_root(tmp_path / "install", None)
    _write_json(install / "hooks.json", {"hooks": {}})

    found, error = drift.install_registrations(install, model.CLAUDE_SCHEMA)

    assert (found, error) == (set(), None)


def test_install_registrations_reads_a_missing_plugin_manifest_as_no_hooks(tmp_path) -> None:
    # plugin.json is optional; without it Claude Code uses the standard layout.
    install = tmp_path / "install"
    install.mkdir()

    found, error = drift.install_registrations(install, model.CLAUDE_SCHEMA)

    assert (found, error) == (set(), None)


def test_compare_install_reports_no_drift_for_an_install_without_a_manifest(tmp_path) -> None:
    install = _plugin_root(tmp_path / "install", None)

    report = drift.compare_install("Claude Code", install, set())

    assert not report.has_drift
    assert report.error is None


def test_compare_install_names_source_hooks_a_manifestless_install_lacks(tmp_path) -> None:
    # Reading absence as "no hooks" must not hide drift: when the source ships
    # a hook, an install that registers nothing still differs from it.
    source_root = _plugin_root(tmp_path / "src", _claude_hooks("guard.py"))
    install = _plugin_root(tmp_path / "install", None)
    source, _ = model.root_registrations(source_root, model.CLAUDE_SCHEMA)

    report = drift.compare_install("Claude Code", install, source or set())

    assert report.has_drift
    assert report.error is None
    assert len(report.only_in_source) == 1


def test_install_registrations_keeps_a_broken_claude_manifest_an_error(tmp_path) -> None:
    install = _plugin_root(tmp_path / "install", None)
    (install / "hooks").mkdir()
    (install / "hooks" / "hooks.json").write_text("{not json", encoding="utf-8")

    found, error = drift.install_registrations(install, model.CLAUDE_SCHEMA)

    assert found is None
    assert "unreadable hook manifest" in (error or "")


def test_install_registrations_keeps_a_declared_hooks_path_an_error(tmp_path) -> None:
    # plugin.json can point hooks elsewhere; this check does not follow that
    # pointer, so absence of the default file proves nothing.
    install = tmp_path / "install"
    _write_json(
        install / ".claude-plugin" / "plugin.json",
        {"name": PLUGIN_NAME, "hooks": "./custom/hooks.json"},
    )

    found, error = drift.install_registrations(install, model.CLAUDE_SCHEMA)

    assert found is None
    assert "no hook manifest" in (error or "")


def test_install_registrations_keeps_an_unreadable_plugin_manifest_an_error(tmp_path) -> None:
    install = tmp_path / "install"
    (install / ".claude-plugin").mkdir(parents=True)
    (install / ".claude-plugin" / "plugin.json").write_text("{not json", encoding="utf-8")

    found, error = drift.install_registrations(install, model.CLAUDE_SCHEMA)

    assert found is None
    assert "no hook manifest" in (error or "")


def test_install_registrations_keeps_an_absent_copilot_manifest_an_error(tmp_path) -> None:
    # Copilot CLI also loads a root hooks.json, so absence of hooks/hooks.json
    # is not proof of zero hooks there.
    install = _plugin_root(tmp_path / "install", None)

    found, error = drift.install_registrations(install, model.COPILOT_SCHEMA)

    assert found is None
    assert "no hook manifest" in (error or "")


def test_root_registrations_keeps_an_absent_source_manifest_an_error(tmp_path) -> None:
    # The source side stays strict: a checkout missing its manifest is a
    # broken checkout, not a plugin that ships no hooks.
    source_root = _plugin_root(tmp_path / "src", None)

    found, error = model.root_registrations(source_root, model.CLAUDE_SCHEMA)

    assert found is None
    assert "no hook manifest" in (error or "")
