#!/usr/bin/env python3
"""Tests for the generator's dispatch-group expansion (#3075).

The Copilot tree must be generated from the PER-HOOK view, not the
consolidated dispatcher registrations, so `_expand_dispatch_groups` has to
reproduce the pre-consolidation command/timeout/statusMessage entries
exactly. These tests exercise the expansion against both fixtures and the
real committed settings + manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPTS = str(REPO_ROOT / "build" / "scripts")
if BUILD_SCRIPTS not in sys.path:
    sys.path.insert(0, BUILD_SCRIPTS)

from generate_hooks_events import (  # noqa: E402
    GenerateHooksError,
    _expand_dispatch_groups,
)

HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def _fixture_manifest(tmp_path: Path, groups: dict) -> Path:
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "dispatch_groups.json").write_text(
        json.dumps({"groups": groups}), encoding="utf-8"
    )
    return hooks_dir


def test_expands_dispatcher_registration_to_member_hooks(tmp_path):
    hooks_dir = _fixture_manifest(
        tmp_path,
        {
            "g1": {
                "event": "PreToolUse",
                "mode": "gate",
                "matcher": "Bash",
                "shims": [
                    {"file": "a.py", "timeout": 5, "statusMessage": "A"},
                    {"file": "Sub/b.py"},
                ],
            }
        },
    )
    hooks_map = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                        "timeout": 60,
                    }
                ],
            }
        ]
    }
    out = _expand_dispatch_groups(hooks_map, hooks_dir)
    groups = out["PreToolUse"]
    assert len(groups) == 1
    assert groups[0]["matcher"] == "Bash"
    assert groups[0]["hooks"] == [
        {
            "type": "command",
            "command": "python3 -u .claude/hooks/a.py",
            "timeout": 5,
            "statusMessage": "A",
        },
        {"type": "command", "command": "python3 -u .claude/hooks/Sub/b.py"},
    ]


def test_copilot_matcher_override_splits_partitions(tmp_path):
    hooks_dir = _fixture_manifest(
        tmp_path,
        {
            "g1": {
                "event": "PreToolUse",
                "mode": "gate",
                "matcher": "^(Write|Edit)$",
                "shims": [
                    {"file": "a.py"},
                    {"file": "b.py", "copilotMatcher": "^(Edit|Write)$"},
                ],
            }
        },
    )
    hooks_map = {
        "PreToolUse": [
            {
                "matcher": "^(Write|Edit)$",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                    }
                ],
            }
        ]
    }
    out = _expand_dispatch_groups(hooks_map, hooks_dir)
    matchers = [g["matcher"] for g in out["PreToolUse"]]
    assert matchers == ["^(Write|Edit)$", "^(Edit|Write)$"]


def test_non_dispatcher_groups_pass_through_unchanged(tmp_path):
    hooks_dir = _fixture_manifest(tmp_path, {})
    original = {
        "PreToolUse": [
            {
                "matcher": "Grep",
                "hooks": [
                    {"type": "command", "command": "python3 -u .claude/hooks/x.py"}
                ],
            }
        ]
    }
    out = _expand_dispatch_groups(original, hooks_dir)
    assert out == original


def test_unknown_group_raises(tmp_path):
    hooks_dir = _fixture_manifest(tmp_path, {})
    hooks_map = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group nope",
                    }
                ],
            }
        ]
    }
    with pytest.raises(GenerateHooksError):
        _expand_dispatch_groups(hooks_map, hooks_dir)


def test_event_mismatch_raises(tmp_path):
    hooks_dir = _fixture_manifest(
        tmp_path,
        {"g1": {"event": "Stop", "mode": "gate_all", "matcher": None, "shims": []}},
    )
    hooks_map = {
        "PreToolUse": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                    }
                ]
            }
        ]
    }
    with pytest.raises(GenerateHooksError):
        _expand_dispatch_groups(hooks_map, hooks_dir)


def test_dispatcher_mixed_with_sibling_hook_raises(tmp_path):
    hooks_dir = _fixture_manifest(
        tmp_path,
        {"g1": {"event": "PreToolUse", "mode": "gate", "matcher": "Bash", "shims": []}},
    )
    hooks_map = {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "python3 -u .claude/hooks/invoke_dispatch_claude.py --group g1",
                    },
                    {"type": "command", "command": "python3 -u .claude/hooks/other.py"},
                ],
            }
        ]
    }
    with pytest.raises(GenerateHooksError):
        _expand_dispatch_groups(hooks_map, hooks_dir)


def test_real_settings_expand_cleanly_with_no_dispatcher_residue():
    settings = json.loads(
        (REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    out = _expand_dispatch_groups(settings["hooks"], HOOKS_DIR)
    commands = [
        hook.get("command", "")
        for groups in out.values()
        for group in groups
        if isinstance(group, dict)
        for hook in group.get("hooks", [])
        if isinstance(hook, dict)
    ]
    assert commands, "expansion must not empty the hook map"
    assert not any("invoke_dispatch_claude.py" in cmd for cmd in commands)
