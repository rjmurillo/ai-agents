"""Read-only agents hold no write or shell tool on the Claude surface (issues #5767, #5356).

`analyst`, `security`, `code-reviewer`, and `comment-analyzer` are read-only by
contract. On Claude Code an agent with no `tools:` key inherits every session
tool, including MCP servers whose names vary by install. ADR-107 ("Read-only
agents inherit tools") therefore gives these four no `tools:` key and a
`disallowedTools:` deny list. This module pins that shape in the shipped plugin
tree and the binplaced install tree: no `tools:` grant, and every built-in shell
and file mutator denied by name.

`security` keeps the #5356 control here: its enforcement is that `Bash` is
denied, so mutating git and git config injection are unreachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
READ_ONLY_AGENTS = ("analyst", "security", "code-reviewer", "comment-analyzer")
AGENT_TREES = (REPO_ROOT / "src" / "claude" / "agents", REPO_ROOT / ".claude" / "agents")
FORBIDDEN = frozenset({"Bash", "Edit", "Write", "NotebookEdit", "MultiEdit"})


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    _, block, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(block)
    assert isinstance(loaded, dict), f"{path} frontmatter is not a mapping"
    return loaded


def _denied(path: Path) -> set[str]:
    """Return ``disallowedTools``, failing when the agent also grants a ``tools`` list."""
    frontmatter = _frontmatter(path)
    assert frontmatter.get("tools") is None, (
        f"{path} declares a `tools` allowlist; ADR-107 read-only agents inherit tools "
        f"and subtract through `disallowedTools`."
    )
    denied = frontmatter.get("disallowedTools")
    assert isinstance(denied, list), (
        f"{path} has no disallowedTools list, so Claude Code grants it every tool, "
        f"including Bash, Edit, and Write."
    )
    return {str(tool) for tool in denied}


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_read_only_agent_denies_every_write_and_shell_tool(agent: str, tree: Path) -> None:
    denied = _denied(tree / f"{agent}.md")

    missing = FORBIDDEN - denied
    assert not missing, (
        f"{agent} in {tree} is read-only by contract but does not deny {sorted(missing)}."
    )
    assert "Agent" in denied, f"{agent} is a worker and must deny Agent (check_agent_delegation)"


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_read_only_agent_denies_mcp_writes_under_every_prefix_variant(
    agent: str, tree: Path
) -> None:
    denied = _denied(tree / f"{agent}.md")

    for prefix in (
        "mcp__serena",
        "mcp__plugin_serena_serena",
        "mcp__claude_ai_Serena",
        "mcp__github",
        "mcp__plugin_github_github",
        "mcp__claude_ai_GitHub",
    ):
        tool = "write_memory" if "serena" in prefix.lower() else "merge_pull_request"
        assert f"{prefix}__{tool}" in denied, f"{agent} does not deny {prefix}__{tool}"


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_read_only_agent_keeps_mcp_read_tools(agent: str, tree: Path) -> None:
    denied = _denied(tree / f"{agent}.md")

    for read_tool in (
        "mcp__serena__read_memory",
        "mcp__serena__find_symbol",
        "mcp__github__pull_request_read",
        "mcp__github__get_file_contents",
    ):
        assert read_tool not in denied


def test_missing_deny_list_is_detected(tmp_path: Path) -> None:
    """Negative control: an agent with neither key inherits every tool."""
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: agent\ndescription: x\n---\nbody\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="no disallowedTools"):
        _denied(agent)


def test_tools_allowlist_is_rejected(tmp_path: Path) -> None:
    """Negative control: a template granting Bash through `tools` fails the check."""
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: agent\ntools:\n  - Read\n  - Bash\n---\nbody\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="declares a `tools` allowlist"):
        _denied(agent)


def test_partial_deny_list_leaves_a_mutator_uncovered(tmp_path: Path) -> None:
    """Negative control: denying Bash alone leaves Edit, Write, and the rest open."""
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: agent\ndisallowedTools:\n  - Bash\n---\nbody\n", encoding="utf-8")

    assert FORBIDDEN - _denied(agent) == {"Edit", "Write", "NotebookEdit", "MultiEdit"}
