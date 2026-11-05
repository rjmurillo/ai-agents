"""Guard the plugin hook file location (ADR-109 section 2 amendment, 2026-11-04).

Claude Code auto-discovers plugin hooks only at ``<plugin-root>/hooks/hooks.json``.
At the old plugin-root path a live ``--plugin-dir`` run registered 22 hooks and
never ran the Stop hook (REQ-048 TASK-006, owner decision D28). A ``hooks`` key
in ``plugin.json`` is banned by ``validate_plugin_manifests.py`` (issue #1833),
so the file location is the only registration path.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "src" / "claude"
PLUGIN_HOOKS = PLUGIN_ROOT / "hooks" / "hooks.json"
OLD_PLUGIN_ROOT_HOOKS = PLUGIN_ROOT / "hooks.json"
PLUGIN_MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
DOGFOOD_LINK = REPO_ROOT / ".claude" / "hooks" / "hooks.json"
STOP_GROUP = "plugin-stop-1-reflect_nudge"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plugin_hooks_file_sits_where_claude_code_discovers_it() -> None:
    assert PLUGIN_HOOKS.is_file()
    assert "hooks" in _load(PLUGIN_HOOKS)


def test_plugin_hooks_file_registers_the_stop_group() -> None:
    stop_groups = _load(PLUGIN_HOOKS)["hooks"].get("Stop", [])
    commands = [hook["command"] for group in stop_groups for hook in group["hooks"]]
    assert any(f"--group {STOP_GROUP}" in command for command in commands)


def test_nothing_renders_at_the_old_plugin_root_path() -> None:
    assert not OLD_PLUGIN_ROOT_HOOKS.exists()


def test_plugin_manifest_declares_no_hooks_key() -> None:
    assert "hooks" not in _load(PLUGIN_MANIFEST)


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs Developer Mode on Windows"
)
def test_dogfood_hooks_json_is_a_relative_link_to_the_plugin_file() -> None:
    assert DOGFOOD_LINK.is_symlink()
    assert os.readlink(DOGFOOD_LINK) == "../../src/claude/hooks/hooks.json"
    assert DOGFOOD_LINK.resolve() == PLUGIN_HOOKS.resolve()
