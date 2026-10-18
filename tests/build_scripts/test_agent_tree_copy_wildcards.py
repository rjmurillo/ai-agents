"""Cursor `readonly` for MCP server wildcards (ADR-107 amendment 2026-10-17).

Split from ``test_agent_tree_copy.py`` to keep that file under the size limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import agent_tree_copy as atc  # noqa: E402


@pytest.mark.parametrize(
    "wildcard",
    ["mcp__context7__*", "mcp__plugin_context7_context7__*", "mcp__claude_ai_Context7__*"],
)
def test_wildcard_of_a_whole_grant_server_is_readonly(wildcard: str) -> None:
    assert atc.is_readonly_tool(wildcard)
    assert atc.derive_readonly({"tools": ["Read", wildcard, "ToolSearch"]})
    assert atc.has_inexpressible_restriction({"tools": ["Write", wildcard]})


@pytest.mark.parametrize(
    "wildcard",
    [
        "mcp__serena__*",
        "mcp__github__*",
        "mcp__deepwiki__*",
        "mcp__claude_ai_Slack__*",
        "mcp__plugin_context7_evil__*",
        "mcp__claude_ai_context7__*",
    ],
)
def test_wildcard_of_any_other_server_is_not_readonly(wildcard: str) -> None:
    assert not atc.is_readonly_tool(wildcard)
    assert not atc.derive_readonly({"tools": ["Read", wildcard]})


def test_wildcard_does_not_hide_a_write_builtin() -> None:
    assert not atc.derive_readonly({"tools": ["Read", "Write", "mcp__context7__*"]})
