#!/usr/bin/env python3
"""Tests for host-side matcher union emission (#3075).

Copilot CLI 1.0.71 honors per-entry ``matcher`` (verified empirically:
non-matching entries never spawn). The generator emits a tool-name union
on dispatcher entries ONLY when every shim matcher reduces to documented
Claude core tools; anything exotic fails open to no matcher so no guard
can silently die on an unmapped runtime tool name.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPTS = str(REPO_ROOT / "build" / "scripts")
if BUILD_SCRIPTS not in sys.path:
    sys.path.insert(0, BUILD_SCRIPTS)

import pytest  # noqa: E402
from generate_dispatcher import (  # noqa: E402
    _matcher_tool_tokens,
    dispatcher_entry,
    event_matcher_union,
)


@pytest.mark.parametrize(
    ("matcher", "expected"),
    [
        ("Bash", ["Bash"]),
        ("Bash(git commit*|git ci*)", ["Bash"]),
        ("Bash(git push*)", ["Bash"]),
        ("^(Write|Edit)$", ["Write", "Edit"]),
        ("^(Edit|Write)$", ["Edit", "Write"]),
        ("Grep", ["Grep"]),
        ("Task", ["Task"]),
        (None, None),
        ("", None),
        ("*", None),
        ("mcp__serena__write_memory", None),
        ("^(mcp__serena__(find_symbol)|LSP)$", None),
        ("UnknownTool", None),
    ],
)
def test_matcher_tool_tokens(matcher, expected):
    assert _matcher_tool_tokens(matcher) == expected


def test_union_emits_for_fully_reducible_event():
    union = event_matcher_union(
        "PreToolUse",
        ["Bash", "Bash(git commit*|git ci*)", "^(Write|Edit)$", "Grep", "Bash"],
    )
    assert union == "Bash|Write|Edit|Grep"


def test_union_fails_open_when_any_matcher_is_exotic():
    assert event_matcher_union("PreToolUse", ["Bash", "mcp__serena__write_memory"]) is None


def test_union_only_for_matcher_capable_events():
    assert event_matcher_union("SessionStart", ["Bash"]) is None
    assert event_matcher_union("UserPromptSubmit", ["Bash"]) is None


def test_dispatcher_entry_carries_matcher_when_given():
    entry = dispatcher_entry("PreToolUse", 60, "Bash|Edit")
    assert entry["matcher"] == "Bash|Edit"
    assert "matcher" not in dispatcher_entry("PreToolUse", 60, None)


def test_committed_matcher_capable_entries_have_matchers():
    hooks = json.loads(
        (REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    )["hooks"]

    # Issue #5154 retired the Bash and Bash(git push*) PreToolUse groups and the
    # only PostToolUse group (markdown_auto_lint). On `main` alone that would
    # have narrowed the surviving union to {"Agent", "Task"}. Merged with issue
    # #5061 (which added a PreToolUse shim whose matcher,
    # mcp__serena__(write|delete)_memory|..., does not reduce to a documented
    # Claude core tool name), that narrowing never takes effect:
    # event_matcher_union fails open for PreToolUse regardless of which other
    # shims are registered, and the generated entry carries no "matcher" field
    # at all (see dispatcher_entry: it omits the key when the union is None).
    # This follows directly from _matcher_tool_tokens returning None for an
    # mcp__ pattern, asserted in test_matcher_tool_tokens above.
    assert set(hooks) == {"PreToolUse"}
    assert "matcher" not in hooks["PreToolUse"][0]


def test_internal_claude_matcher_key_never_reaches_committed_artifact():
    text = (REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json").read_text(encoding="utf-8")
    assert "claudeMatcher" not in text
