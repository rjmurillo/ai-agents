"""AC3 of issue #4229: the installed context-mode plugin still hooks WebFetch.

The research command's recovery path exists because context-mode registers a
PreToolUse hook that denies WebFetch. This check reads the plugin Claude Code
actually loads, so it fails when that hook is removed or renamed.

It resolves the active install from ``installed_plugins.json``, not from the
plugin cache. The cache keeps every version ever installed, so a glob over it
picks a stale directory (2026-11-09: it picked 2.0.2 while 2.1.7 was active).
The hook file is the one ``.claude-plugin/plugin.json`` names under ``hooks``,
or ``hooks/hooks.json`` when that key is absent. context-mode 2.x names
``./hooks/claude-code.json``.

When no install is recorded the check skips, so CI stays green without it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_PLUGIN_KEY = "context-mode@context-mode"
_DEFAULT_HOOKS_FILE = "hooks/hooks.json"


def _installed_plugins_file(home: Path) -> Path:
    return home / ".claude" / "plugins" / "installed_plugins.json"


def active_install_path(home: Path, key: str = _PLUGIN_KEY) -> Path | None:
    """Install directory Claude Code records for ``key``, or None."""
    try:
        data = json.loads(_installed_plugins_file(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    plugins = data.get("plugins", data) if isinstance(data, dict) else {}
    entry = plugins.get(key) if isinstance(plugins, dict) else None
    # Schema version 2 stores a list of installs per plugin.
    entries = entry if isinstance(entry, list) else [entry]
    for item in entries:
        path = item.get("installPath") if isinstance(item, dict) else None
        if isinstance(path, str) and Path(path).is_dir():
            return Path(path)
    return None


def hook_events(install: Path) -> dict[str, Any] | None:
    """Event map of the hooks the plugin declares, or None when none is found."""
    declared: object = None
    manifest = install / ".claude-plugin" / "plugin.json"
    try:
        declared = json.loads(manifest.read_text(encoding="utf-8")).get("hooks")
    except (OSError, ValueError, AttributeError):
        declared = None
    if isinstance(declared, dict):
        document: object = declared
    else:
        relative = declared if isinstance(declared, str) else _DEFAULT_HOOKS_FILE
        try:
            document = json.loads((install / relative).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    if not isinstance(document, dict):
        return None
    events = document.get("hooks", document)
    return events if isinstance(events, dict) else None


def test_context_mode_plugin_hooks_json_contains_webfetch_matcher() -> None:
    """AC3: the active install registers a PreToolUse handler for WebFetch."""
    install = active_install_path(Path.home())
    if install is None:
        pytest.skip("context-mode plugin not installed")
    events = hook_events(install)
    assert events is not None, f"no hook manifest found under {install}"
    matchers = [group.get("matcher", "") for group in events.get("PreToolUse", [])]
    assert any("WebFetch" in matcher for matcher in matchers), (
        f"{install}: no PreToolUse entry matching WebFetch; "
        "the hook that triggers the reroute defect was removed or renamed"
    )


# --- resolver tests (no install needed) ----------------------------------------


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _install(home: Path, version: str, entry_as_list: bool = True) -> Path:
    install = home / "cache" / version
    install.mkdir(parents=True)
    entry = {"scope": "user", "installPath": str(install), "version": version}
    _write(
        _installed_plugins_file(home),
        {"version": 2, "plugins": {_PLUGIN_KEY: [entry] if entry_as_list else entry}},
    )
    return install


def test_resolver_picks_the_recorded_install_not_the_highest_cached_one(tmp_path: Path) -> None:
    active = _install(tmp_path, "2.1.7")
    (tmp_path / "cache" / "2.0.2").mkdir()
    assert active_install_path(tmp_path) == active


def test_resolver_accepts_a_single_entry_and_skips_a_missing_directory(tmp_path: Path) -> None:
    active = _install(tmp_path, "1.0.169", entry_as_list=False)
    assert active_install_path(tmp_path) == active
    active.rmdir()
    assert active_install_path(tmp_path) is None


def test_resolver_returns_none_without_an_install_record(tmp_path: Path) -> None:
    assert active_install_path(tmp_path) is None


def test_hooks_come_from_the_file_plugin_json_names(tmp_path: Path) -> None:
    install = _install(tmp_path, "2.1.7")
    _write(install / ".claude-plugin" / "plugin.json", {"hooks": "./hooks/claude-code.json"})
    _write(
        install / "hooks" / "claude-code.json",
        {"hooks": {"PreToolUse": [{"matcher": "^(WebFetch)$"}]}},
    )
    _write(install / "hooks" / "hooks.json", {"hooks": {}})
    assert hook_events(install) == {"PreToolUse": [{"matcher": "^(WebFetch)$"}]}


def test_hooks_fall_back_to_hooks_json_without_a_manifest_key(tmp_path: Path) -> None:
    install = _install(tmp_path, "1.0.169")
    _write(install / ".claude-plugin" / "plugin.json", {"name": "context-mode"})
    _write(install / "hooks" / "hooks.json", {"hooks": {"Stop": []}})
    assert hook_events(install) == {"Stop": []}


def test_inline_hooks_in_plugin_json_are_read_directly(tmp_path: Path) -> None:
    install = _install(tmp_path, "3.0.0")
    _write(install / ".claude-plugin" / "plugin.json", {"hooks": {"PreToolUse": []}})
    assert hook_events(install) == {"PreToolUse": []}


def test_a_missing_hook_file_yields_none(tmp_path: Path) -> None:
    install = _install(tmp_path, "2.1.7")
    _write(install / ".claude-plugin" / "plugin.json", {"hooks": "./hooks/absent.json"})
    assert hook_events(install) is None
