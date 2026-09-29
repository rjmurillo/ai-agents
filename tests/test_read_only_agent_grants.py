"""Read-only agents hold no write or shell tool on the Claude surface (issue #5767).

`code-reviewer` and `comment-analyzer` promise in their own contracts that they
never edit, stage, or run commands. On Claude Code an agent with no `tools:`
key inherits every tool, so that promise was prose only. ADR-112 maps both to
the read-only tier and grants them an explicit list. This module pins the list
in the shipped plugin tree and the binplaced install tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
READ_ONLY_AGENTS = ("code-reviewer", "comment-analyzer")
AGENT_TREES = (REPO_ROOT / "src" / "claude" / "agents", REPO_ROOT / ".claude" / "agents")
FORBIDDEN = frozenset({"Bash", "Edit", "Write", "NotebookEdit", "MultiEdit"})


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    _, block, _ = text.split("---\n", 2)
    loaded = yaml.safe_load(block)
    assert isinstance(loaded, dict), f"{path} frontmatter is not a mapping"
    return loaded


def _tools(path: Path) -> list[str]:
    tools = _frontmatter(path).get("tools")
    assert isinstance(tools, list), (
        f"{path} has no tools list, so Claude Code grants it every tool, "
        f"including Bash, Edit, and Write."
    )
    return [str(tool) for tool in tools]


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_read_only_agent_grants_no_write_or_shell(agent: str, tree: Path) -> None:
    granted = set(_tools(tree / f"{agent}.md"))

    assert granted.isdisjoint(FORBIDDEN), (
        f"{agent} in {tree} is read-only by contract but holds "
        f"{sorted(granted & FORBIDDEN)}."
    )
    assert {"Read", "Grep", "Glob"} <= granted


def test_missing_tools_key_is_detected(tmp_path: Path) -> None:
    """Negative control: an agent with no tools key fails the check."""
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: agent\ndescription: x\n---\nbody\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="no tools list"):
        _tools(agent)


def test_forbidden_tool_is_detected(tmp_path: Path) -> None:
    """Negative control: a granted Bash tool intersects the forbidden set."""
    agent = tmp_path / "agent.md"
    agent.write_text(
        "---\nname: agent\ntools:\n  - Read\n  - Bash\n---\nbody\n", encoding="utf-8"
    )

    assert set(_tools(agent)) & FORBIDDEN == {"Bash"}
