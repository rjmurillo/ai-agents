"""Read-only agents hold no shell or local editor on the Claude surface (issues #5767, #5356).

`analyst`, `security`, `code-reviewer`, and `comment-analyzer` are read-only by
contract. On Claude Code an agent with no `tools:` key inherits every session
tool, including MCP servers whose names vary by install. ADR-107 ("Read-only
agents inherit tools") gives these four no `tools:` key and a `disallowedTools:`
list that enforces only the #5356 invariant: no shell and no local file mutation.
Remote write tools follow the user's permission rules.

An agent never loses a capability it held on origin/main. `LEGACY_ALLOWLISTS`
pins each agent's `tools:` list from origin/main at 44fd46a46e (2026-10-17), and
no entry of it may appear in the rendered deny list.
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
# The #5356 invariant. `security` keeps Write, so Write is required of the others only.
SHELL_AND_EDITORS = frozenset({"Bash", "Edit", "MultiEdit", "NotebookEdit"})
SERENA_LOCAL = ("execute_shell_command", "create_text_file", "replace_content", "rename_symbol")


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
def test_read_only_agent_denies_the_shell_and_the_editors(agent: str, tree: Path) -> None:
    denied = _denied(tree / f"{agent}.md")

    required = SHELL_AND_EDITORS if agent == "security" else SHELL_AND_EDITORS | {"Write"}
    assert not required - denied, f"{agent} in {tree} does not deny {sorted(required - denied)}"
    assert "Agent" in denied, f"{agent} is a worker and must deny Agent (check_agent_delegation)"


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_read_only_agent_denies_serena_local_mutators(agent: str, tree: Path) -> None:
    denied = _denied(tree / f"{agent}.md")

    for tool in SERENA_LOCAL:
        assert f"mcp__serena__{tool}" in denied, f"{agent} does not deny mcp__serena__{tool}"


@pytest.mark.parametrize("tree", AGENT_TREES, ids=lambda tree: tree.parent.name)
@pytest.mark.parametrize("agent", READ_ONLY_AGENTS)
def test_no_origin_main_capability_is_denied(agent: str, tree: Path) -> None:
    """Owner decision D3: deny an invariant item only if the agent lacked it before."""
    denied = _denied(tree / f"{agent}.md")

    removed = sorted(denied & set(LEGACY_ALLOWLISTS[agent]))
    assert not removed, f"{agent} lost capabilities it held on origin/main: {removed}"


def test_security_keeps_write_and_serena_memory_writes() -> None:
    denied = _denied(AGENT_TREES[0] / "security.md")

    assert denied.isdisjoint({"Write", "mcp__serena__write_memory", "mcp__serena__edit_memory"})


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


def test_partial_deny_list_leaves_an_editor_uncovered(tmp_path: Path) -> None:
    """Negative control: denying Bash alone leaves the editors open."""
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: agent\ndisallowedTools:\n  - Bash\n---\nbody\n", encoding="utf-8")

    assert SHELL_AND_EDITORS - _denied(agent) == {"Edit", "MultiEdit", "NotebookEdit"}
