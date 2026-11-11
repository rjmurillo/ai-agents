"""Tool-list classification for ``agent_tree_copy.py`` (ADR-115 Decisions 2, 3 and 7).

Decides what an agent's frontmatter ``tools`` declares: whether it declares any,
whether every tool is read-only (so ``readonly: true`` is honest), and whether
the list restricts the agent in a way ``readonly`` cannot express.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))

from agent_capabilities import load_mcp_table, wildcard_grants  # noqa: E402

_READONLY_TOOLS = frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch", "ToolSearch"})
# An MCP tool name is `mcp__<server>__<words>`, the words joined by `_`. It is
# read-only when a read verb leads the words (`get_file_contents`) or the last
# word is `read` (`issue_read`), and no word names a mutation (`find_and_replace`,
# `get_and_run`). `run` is a noun in `get_workflow_run`, so it is not a mutating
# word; a compound name (`and`, `then`) is rejected instead. `query` is not a
# read word: `mcp__db__query` can run a write. `resolve` and `ask` can lead a
# state change (`resolve_review_thread`), so only the exact names in
# _READ_NAMES earn readonly through them.
# A server-level wildcard (`mcp__context7__*`, ADR-107) is read-only only when
# `templates/agent-mcp-servers.yaml` lets that server be granted whole. A
# wildcard for any other server (`mcp__github__*`, `mcp__serena__*`) can carry
# write or shell tools, so it never earns `readonly: true`.
# An unfamiliar name matches none of these and never earns `readonly: true`.
_READ_WORDS = frozenset({"get", "list", "read", "find", "search", "initial"})
_READ_NAMES = frozenset({"resolve_library_id"})
_COMPOUND_WORDS = frozenset({"and", "or", "then"})
_MUTATING_WORDS = frozenset(
    {
        "write", "edit", "create", "update", "delete", "add", "merge", "push", "replace",
        "insert", "rename", "remove", "apply", "move", "fork",
        "exec", "execute", "send", "post", "set", "close", "dispatch",
    }
)  # fmt: skip


class AgentCopyError(Exception):
    """A platform stanza or a source agent file is unusable."""


@functools.cache
def _readonly_wildcards() -> frozenset[str]:
    """Return the ``<prefix>__*`` grants of the servers the MCP table marks safe whole."""
    grants: frozenset[str] = wildcard_grants(load_mcp_table(_SCRIPT_DIR.parents[1]))
    return grants


def is_readonly_tool(tool: object) -> bool:
    """True when ``tool`` names a tool that changes no state."""
    if not isinstance(tool, str):
        return False
    if tool in _READONLY_TOOLS:
        return True
    parts = tool.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return False
    if parts[-1] == "*":
        return tool in _readonly_wildcards()
    words = parts[-1].split("_")
    if any(word in _MUTATING_WORDS or word in _COMPOUND_WORDS for word in words):
        return False
    return parts[-1] in _READ_NAMES or words[0] in _READ_WORDS or words[-1] == "read"


def declared_tools(frontmatter: dict[str, object]) -> list[object] | None:
    """The agent's ``tools`` as a list, or ``None`` when it declares none.

    Claude Code accepts a YAML list or a comma-separated string
    (``tools: Read, Write``, see ``generate_agents_common.py``); both are
    restrictions. Any other non-null type is an error, so the build fails
    instead of shipping an unrestricted agent.
    """
    tools = frontmatter.get("tools")
    if tools is None:
        return None
    if isinstance(tools, list):
        return list(tools)
    if isinstance(tools, str):
        return [name for name in (part.strip() for part in tools.split(",")) if name]
    raise AgentCopyError(
        f"`tools` must be a list or a comma-separated string, got {type(tools).__name__}"
    )


def derive_readonly(frontmatter: dict[str, object]) -> bool:
    """True when the agent declares tools and every one is read-only."""
    tools = declared_tools(frontmatter)
    return bool(tools) and all(is_readonly_tool(tool) for tool in tools or [])


def has_inexpressible_restriction(frontmatter: dict[str, object]) -> bool:
    """True when ``tools`` restricts the agent in a way ``readonly`` cannot express.

    An empty list or empty string restricts the agent to nothing. Cursor has no
    way to say that, so it fails closed like any other non-read-only list.
    """
    return declared_tools(frontmatter) is not None and not derive_readonly(frontmatter)
