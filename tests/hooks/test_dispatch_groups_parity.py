#!/usr/bin/env python3
"""Parity checks between hook registrations and dispatch_groups.json (#3075).

The dispatch manifest is the source of truth for group membership. These
tests keep the three surfaces honest: repo settings (.claude/settings.json),
the project-toolkit plugin manifest (.claude/hooks/hooks.json), and the
files on disk. A registration that names a missing group, a group whose
event or matcher disagrees with its registration, or a shim file that does
not exist would otherwise fail at hook time (fail-closed) for every tool
call in the group.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
MANIFEST = json.loads((HOOKS_DIR / "dispatch_groups.json").read_text(encoding="utf-8"))
SETTINGS = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
PLUGIN_HOOKS = json.loads((HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))

_GROUP_RE = re.compile(r"dispatch_claude\.py\"?\s+--group\s+([A-Za-z0-9_-]+)")
_DEFAULT_SHIM_TIMEOUT = 30
_DISPATCHER_HEADROOM = 5


def _dispatch_registrations(hooks_map: dict) -> list[tuple[str, str | None, str]]:
    """Yield (event, matcher, group_id) for every dispatcher registration."""
    found = []
    for event, groups in hooks_map.items():
        for group in groups:
            for hook in group.get("hooks", []):
                match = _GROUP_RE.search(hook.get("command", "") or "")
                if match:
                    found.append((event, group.get("matcher"), match.group(1)))
    return found


SETTINGS_REGS = _dispatch_registrations(SETTINGS["hooks"])
PLUGIN_REGS = _dispatch_registrations(PLUGIN_HOOKS["hooks"])


def test_every_manifest_shim_exists_on_disk():
    missing = [
        f"{group_id}: {shim['file']}"
        for group_id, spec in MANIFEST["groups"].items()
        for shim in spec["shims"]
        if not (HOOKS_DIR / shim["file"]).is_file()
    ]
    assert missing == []


@pytest.mark.parametrize(("event", "matcher", "group_id"), SETTINGS_REGS)
def test_settings_registrations_match_manifest(event, matcher, group_id):
    spec = MANIFEST["groups"].get(group_id)
    assert spec is not None, f"settings.json references unknown group {group_id}"
    assert spec["event"] == event
    assert spec.get("matcher") == matcher
    assert spec.get("surface") != "plugin", (
        f"settings.json must not register plugin-surface group {group_id}"
    )


def test_settings_dispatcher_timeouts_cover_serial_members_and_headroom():
    timeout_by_group = {
        match.group(1): hook["timeout"]
        for groups in SETTINGS["hooks"].values()
        for group in groups
        for hook in group.get("hooks", [])
        if (match := _GROUP_RE.search(hook.get("command", "") or ""))
    }
    for group_id, timeout in timeout_by_group.items():
        shims = MANIFEST["groups"][group_id]["shims"]
        required = (
            sum(shim.get("timeout", _DEFAULT_SHIM_TIMEOUT) for shim in shims)
            + _DISPATCHER_HEADROOM
        )
        assert timeout >= required, (
            f"{group_id}: dispatcher timeout {timeout}s is below the "
            f"{required}s serial budget"
        )


@pytest.mark.parametrize(("event", "matcher", "group_id"), PLUGIN_REGS)
def test_plugin_registrations_match_manifest(event, matcher, group_id):
    spec = MANIFEST["groups"].get(group_id)
    assert spec is not None, f"hooks.json references unknown group {group_id}"
    assert spec["event"] == event
    assert spec.get("matcher") == matcher
    assert spec.get("surface") == "plugin", (
        f"plugin hooks.json must register plugin-surface groups, got {group_id}"
    )


def test_settings_uses_every_project_group():
    project_groups = {
        gid for gid, spec in MANIFEST["groups"].items() if spec.get("surface") != "plugin"
    }
    registered = {gid for _, _, gid in SETTINGS_REGS}
    assert registered == project_groups


def test_plugin_uses_every_plugin_group():
    plugin_groups = {
        gid for gid, spec in MANIFEST["groups"].items() if spec.get("surface") == "plugin"
    }
    registered = {gid for _, _, gid in PLUGIN_REGS}
    assert registered == plugin_groups


def test_modes_are_valid_and_event_appropriate():
    for group_id, spec in MANIFEST["groups"].items():
        assert spec["mode"] in {"gate", "gate_all", "observe"}, group_id
        if spec["event"] == "PreToolUse":
            assert spec["mode"] == "gate", (
                f"{group_id}: PreToolUse groups must fail closed (gate mode)"
            )


def _group_shim_basenames(surface_is_plugin: bool) -> set[str]:
    return {
        shim["file"].split("/")[-1]
        for spec in MANIFEST["groups"].values()
        if (spec.get("surface") == "plugin") == surface_is_plugin
        for shim in spec["shims"]
    }


def _settings_direct_basenames() -> set[str]:
    return {
        (hook.get("command") or "").rsplit("/", 1)[-1]
        for groups in SETTINGS["hooks"].values()
        for group in groups
        for hook in group.get("hooks", [])
        if "invoke_dispatch_claude.py" not in (hook.get("command") or "")
    }


def test_repo_settings_cover_plugin_shims_minus_documented_prunes():
    # The self-host bail (invoke_dispatch_claude.py exiting 0 for plugin
    # invocations inside this repo) is only safe when repo settings run
    # every hook the plugin would have run, minus the prunes this repo
    # deliberately made. A plugin shim missing here would silently never
    # run during this repo's own sessions (the 19-day dead-hook class).
    pruned = {
        # ADR-084 keeps customer-value markdown hooks plugin-only.
        "invoke_markdown_auto_lint.py",
        "invoke_markdownlint_guard.py",
    }
    uncovered = (
        _group_shim_basenames(surface_is_plugin=True)
        - _group_shim_basenames(surface_is_plugin=False)
        - _settings_direct_basenames()
    )
    assert uncovered == pruned, (
        f"plugin shims not covered by repo settings (and not documented prunes): "
        f"{sorted(uncovered - pruned)}; stale prune entries: {sorted(pruned - uncovered)}"
    )


def test_plugin_registrations_are_dispatcher_only():
    # Every plugin hook command must route through the dispatcher so the
    # self-host bail applies to the whole plugin surface (no double-fire
    # inside the publishing repo).
    direct = [
        hook.get("command")
        for groups in PLUGIN_HOOKS["hooks"].values()
        for group in groups
        for hook in group.get("hooks", [])
        if "invoke_dispatch_claude.py" not in (hook.get("command") or "")
    ]
    assert direct == []
