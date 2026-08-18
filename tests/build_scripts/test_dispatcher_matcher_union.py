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
        (REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json").read_text(
            encoding="utf-8"
        )
    )["hooks"]
    expected = {
        "PreToolUse": {"Bash", "Agent", "Task"},
        "PostToolUse": {"Write", "Edit"},
    }

    assert set(hooks) == set(expected)
    for event, tokens in expected.items():
        entry = hooks[event][0]
        matcher = entry.get("matcher")
        if event == "PreToolUse":
            # #5036 review: this branch must not silently skip the
            # assertion. The Serena guard's copilotMatcher
            # ("^serena-.*$") is a wildcard regex that _matcher_tool_tokens
            # cannot reduce to a bare-name list (it is not an alternation of
            # known tool names), so event_matcher_union returns None for the
            # WHOLE PreToolUse group and the host-side matcher is dropped:
            # every PreToolUse call spawns this dispatcher. That is a
            # deliberate, documented trade-off (#4917), not a bug, because
            # each wrapped shim script still carries its own embedded
            # _MATCHER and filters internally before doing any real work
            # (proved directly against the committed serena guard shim by
            # tests/hooks/test_serena_worktree_scope_guard.py::
            # TestGeneratedShimIntegration::
            # test_generated_shim_no_ops_for_unrelated_tool). Assert the
            # cause explicitly instead of masking it with `continue`, so a
            # future PreToolUse shim whose matcher becomes reducible again
            # (and therefore SHOULD restore host-side filtering) trips this
            # test instead of passing silently.
            assert matcher is None, (
                f"PreToolUse host matcher is {matcher!r}, expected None. "
                "If every PreToolUse shim's matcher is now reducible to bare "
                f"tool names, update `expected[{event!r}]` to {tokens!r} "
                "instead of leaving this stale."
            )
            continue
        assert set(matcher.split("|")) == tokens


def test_internal_claude_matcher_key_never_reaches_committed_artifact():
    text = (REPO_ROOT / "src" / "copilot-cli" / "hooks" / "hooks.json").read_text(
        encoding="utf-8"
    )
    assert "claudeMatcher" not in text
