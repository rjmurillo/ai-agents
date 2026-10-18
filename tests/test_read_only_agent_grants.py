"""Read-only agents hold no executor on the Claude surface (issues #5767, #5356, ADR-107).

`analyst`, `security`, `code-reviewer`, and `comment-analyzer` are read-only by
contract. Each declares a `tools:` allowlist: its origin/main built-ins plus
`ToolSearch`, and MCP servers granted by wildcard (`$mcp:<server>`, expanded by the
renderer). Wildcard servers that have write tools carry a matching `disallowedTools`
list under the same prefixes. This module pins that shape in the shipped plugin tree
and the binplaced install tree.

`LEGACY_ALLOWLISTS` pins each agent's `tools:` list from origin/main at 44fd46a46e
(2026-10-17). An agent never loses a capability it held there.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_TREES = (REPO_ROOT / "src" / "claude" / "agents", REPO_ROOT / ".claude" / "agents")

_GITHUB_READ = (
    "mcp__github__pull_request_read",
    "mcp__github__get_file_contents",
    "mcp__github__issue_read",
)
_SERENA_SYMBOL_READ = (
    "mcp__serena__find_symbol",
    "mcp__serena__find_referencing_symbols",
    "mcp__serena__get_symbols_overview",
)
LEGACY_ALLOWLISTS: dict[str, tuple[str, ...]] = {
    "analyst": (
        "Read",
        "Glob",
        "Grep",
        "mcp__github__issue_read",
        "mcp__github__pull_request_read",
        "mcp__github__get_file_contents",
        "mcp__github__list_commits",
        "mcp__github__list_workflow_runs",
        "mcp__github__get_workflow_run",
        "mcp__github__get_job_logs",
        *_SERENA_SYMBOL_READ,
        "mcp__serena__find_implementations",
        "mcp__serena__get_diagnostics_for_file",
        "mcp__serena__find_declaration",
        "mcp__serena__list_memories",
        "mcp__serena__read_memory",
        "mcp__serena__initial_instructions",
        "mcp__context7__resolve_library_id",
        "mcp__context7__get_library_docs",
        "mcp__deepwiki__read_wiki_structure",
        "mcp__deepwiki__read_wiki_contents",
    ),
    "security": (
        "Read",
        "Grep",
        "Glob",
        "WebSearch",
        "WebFetch",
        "TodoWrite",
        "Write",
        "mcp__github__pull_request_read",
        "mcp__github__get_commit",
        "mcp__github__list_commits",
        "mcp__github__get_file_contents",
        "mcp__github__search_code",
        "mcp__github__issue_read",
        "mcp__serena__list_memories",
        "mcp__serena__read_memory",
        "mcp__serena__write_memory",
        "mcp__serena__edit_memory",
    ),
    "code-reviewer": ("Read", "Grep", "Glob", *_GITHUB_READ, *_SERENA_SYMBOL_READ),
    "comment-analyzer": ("Read", "Grep", "Glob", *_GITHUB_READ, *_SERENA_SYMBOL_READ),
}
READ_ONLY_AGENTS = tuple(LEGACY_ALLOWLISTS)

# Executors and session-state tools a read-only agent must never be granted. Probed
# on Claude Code 2.1.302 (2026-10-17): an inherit-all agent still exposed several of
# these after Bash, Edit, and Write were denied.
FORBIDDEN_BUILTINS = frozenset(
    {
        "Bash",
        "PowerShell",
        "Monitor",
        "Skill",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
        "Agent",
        "Task",
        "CronCreate",
        "CronDelete",
        "CronList",
        "RemoteTrigger",
        "EnterWorktree",
        "ExitWorktree",
        "PushNotification",
    }
)
SERENA_LOCAL = ("execute_shell_command", "create_text_file", "replace_content", "rename_symbol")
SERENA_MEMORY_DELETE = ("delete_memory", "rename_memory")
SERENA_MEMORY_EDIT = ("write_memory", "edit_memory")


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    _, block, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(block)
    assert isinstance(loaded, dict), f"{path} frontmatter is not a mapping"
    return loaded


def _list(path: Path, key: str) -> list[str]:
    value = _frontmatter(path).get(key)
    assert isinstance(value, list), (
        f"{path} has no `{key}` list, so Claude Code grants it every tool, "
        f"including Bash, Edit, and Write."
    )
    return [str(item) for item in value]


def _tools(path: Path) -> list[str]:
    return _list(path, "tools")


def _is_granted(tool: str, tools: list[str], denied: list[str]) -> bool:
    """True when ``tool`` is named or covered by a ``<prefix>__*`` entry, and not denied."""
    if tool in denied:
        return False
    if tool in tools:
        return True
    prefix, _, _ = tool.rpartition("__")
    return f"{prefix}__*" in tools


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_allowlist_contains_no_executor(agent: str, tree: Path) -> None:
    granted = set(_tools(tree / f"{agent}.md"))

    forbidden = FORBIDDEN_BUILTINS | ({"Write"} if agent != "security" else set())
    assert granted.isdisjoint(forbidden), (
        f"{agent} in {tree} holds {sorted(granted & forbidden)}; read-only agents hold no executor."
    )
    assert {"Read", "Grep", "Glob"} <= granted


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_every_origin_main_tool_is_still_granted(agent: str, tree: Path) -> None:
    path = tree / f"{agent}.md"
    tools, denied = _tools(path), _list(path, "disallowedTools")

    lost = [t for t in LEGACY_ALLOWLISTS[agent] if not _is_granted(t, tools, denied)]
    assert not lost, f"{agent} lost capabilities it held on origin/main: {lost}"


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_no_global_mcp_wildcard_is_granted(agent: str, tree: Path) -> None:
    """A bare mcp__* grants no tool on 2.1.302, so it is a silent no-op."""
    tools = _tools(tree / f"{agent}.md")

    assert "mcp__*" not in tools
    assert "mcp__" not in tools


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_serena_is_granted_tool_by_tool_never_by_wildcard(agent: str, tree: Path) -> None:
    """A wildcard plus a deny list would grant any future Serena executor."""
    tools = _tools(tree / f"{agent}.md")

    serena = sorted(t for t in tools if t.startswith("mcp__serena"))
    held = sorted(t for t in LEGACY_ALLOWLISTS[agent] if t.startswith("mcp__serena"))
    assert serena == held


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
def test_context7_wildcard_covers_every_prefix_variant(tree: Path) -> None:
    tools = _tools(tree / "analyst.md")

    for prefix in ("mcp__context7", "mcp__plugin_context7_context7", "mcp__claude_ai_Context7"):
        assert f"{prefix}__*" in tools


def test_missing_allowlist_is_detected(tmp_path: Path) -> None:
    """Negative control: an agent with no tools key inherits every tool."""
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: agent\ndescription: x\n---\nbody\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="no `tools` list"):
        _tools(agent)


def test_executor_grant_is_detected(tmp_path: Path) -> None:
    """Negative control: a granted Bash intersects the forbidden set."""
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: agent\ntools:\n  - Read\n  - Bash\n---\nbody\n", encoding="utf-8")

    assert set(_tools(agent)) & FORBIDDEN_BUILTINS == {"Bash"}


def test_a_denied_tool_is_not_granted_by_its_wildcard() -> None:
    assert not _is_granted(
        "mcp__serena__write_memory", ["mcp__serena__*"], ["mcp__serena__write_memory"]
    )
    assert _is_granted(
        "mcp__serena__read_memory", ["mcp__serena__*"], ["mcp__serena__write_memory"]
    )
    assert not _is_granted("mcp__serena__read_memory", ["Read"], [])
