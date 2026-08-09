"""Structural guards for the analyst tool and delegation contract."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

CLAUDE_CANONICAL = REPO_ROOT / "src" / "claude" / "analyst.md"
CLAUDE_RUNTIME = REPO_ROOT / ".claude" / "agents" / "analyst.md"
SHARED_TEMPLATE = REPO_ROOT / "templates" / "agents" / "analyst.shared.md"
COPILOT_RUNTIME = REPO_ROOT / ".github" / "agents" / "analyst.agent.md"
COPILOT_GENERATED = REPO_ROOT / "src" / "copilot-cli" / "agents" / "analyst.agent.md"
VSCODE_GENERATED = REPO_ROOT / "src" / "vs-code-agents" / "analyst.agent.md"
TOOLSETS = REPO_ROOT / "templates" / "toolsets.yaml"
ORCHESTRATOR_CONTRACTS = (
    REPO_ROOT / "src" / "claude" / "orchestrator.md",
    REPO_ROOT / ".claude" / "agents" / "orchestrator.md",
    REPO_ROOT / "templates" / "agents" / "orchestrator.shared.md",
    REPO_ROOT / ".github" / "agents" / "orchestrator.agent.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "orchestrator.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "orchestrator.agent.md",
)

READ_ONLY_SERENA_OPERATIONS = frozenset(
    {
        "find_declaration",
        "find_implementations",
        "find_referencing_symbols",
        "find_symbol",
        "get_diagnostics_for_file",
        "get_symbols_overview",
        "initial_instructions",
        "list_memories",
        "read_memory",
    }
)
CLAUDE_ALLOWED_TOOLS = frozenset(
    {
        "Glob",
        "Grep",
        "Read",
        "mcp__context7__get_library_docs",
        "mcp__context7__resolve_library_id",
        "mcp__deepwiki__read_wiki_contents",
        "mcp__deepwiki__read_wiki_structure",
        *(f"mcp__serena__{operation}" for operation in READ_ONLY_SERENA_OPERATIONS),
    }
)
PLATFORM_ALLOWED_TOOLS = frozenset(
    {
        "cognitionai/deepwiki/*",
        "context7/*",
        "read",
        "search",
        *(f"serena/{operation}" for operation in READ_ONLY_SERENA_OPERATIONS),
    }
)
UNSAFE_TOOL_PREFIXES = (
    "$toolset:",
    "agent",
    "bash",
    "cloudmcp-manager",
    "edit",
    "execute",
    "memory",
    "notebookedit",
    "perplexity",
    "shell",
    "skill",
    "task",
    "vscode",
    "web",
    "write",
)
UNSAFE_SERENA_OPERATIONS = frozenset(
    {
        "delete_memory",
        "edit_memory",
        "insert_after_symbol",
        "insert_before_symbol",
        "onboarding",
        "rename_memory",
        "rename_symbol",
        "replace_content",
        "replace_in_files",
        "replace_symbol_body",
        "safe_delete_symbol",
        "write_memory",
    }
)


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    assert len(parts) == 3, f"{path} must contain YAML frontmatter"
    parsed = yaml.safe_load(parts[1])
    assert isinstance(parsed, dict), f"{path} frontmatter must be a mapping"
    return parsed


def _tool_list(metadata: dict[str, object], key: str, source: Path) -> list[str]:
    tools = metadata.get(key)
    assert isinstance(tools, list) and tools, f"{source} must declare a non-empty {key}"
    assert all(isinstance(tool, str) for tool in tools), f"{source} {key} must contain strings"
    return tools


def _assert_read_only_tools(tools: list[str], allowed_tools: frozenset[str]) -> None:
    assert tools, "analyst must declare tools explicitly"
    assert len(tools) == len(set(tools)), "analyst tool list contains duplicates"
    assert set(tools) == allowed_tools, (
        f"analyst tool contract mismatch: "
        f"unexpected={sorted(set(tools) - allowed_tools)}, "
        f"missing={sorted(allowed_tools - set(tools))}"
    )
    for tool in tools:
        normalized = tool.casefold()
        base = normalized.split("(", 1)[0]
        assert not base.startswith(UNSAFE_TOOL_PREFIXES), f"analyst grants unsafe tool: {tool}"
        assert not normalized.startswith("github/"), (
            f"analyst grants unavailable GitHub tool: {tool}"
        )

        operation = None
        if normalized.startswith("serena/"):
            operation = normalized.removeprefix("serena/")
        elif normalized.startswith("mcp__serena__"):
            operation = normalized.removeprefix("mcp__serena__")
        if operation is not None:
            assert operation not in UNSAFE_SERENA_OPERATIONS
            assert operation in READ_ONLY_SERENA_OPERATIONS, (
                f"analyst grants unreviewed Serena tool: {tool}"
            )


def test_claude_declares_explicit_read_only_tools() -> None:
    canonical_tools = _tool_list(_frontmatter(CLAUDE_CANONICAL), "tools", CLAUDE_CANONICAL)
    runtime_tools = _tool_list(_frontmatter(CLAUDE_RUNTIME), "tools", CLAUDE_RUNTIME)

    _assert_read_only_tools(canonical_tools, CLAUDE_ALLOWED_TOOLS)
    assert not any(tool.startswith("github/") for tool in canonical_tools)
    assert runtime_tools == canonical_tools


@pytest.mark.parametrize("key", ["tools_copilot", "tools_vscode"])
def test_shared_template_declares_platform_read_only_tools(key: str) -> None:
    tools = _tool_list(_frontmatter(SHARED_TEMPLATE), key, SHARED_TEMPLATE)

    _assert_read_only_tools(tools, PLATFORM_ALLOWED_TOOLS)
    assert not any(tool.startswith("github/") for tool in tools)


@pytest.mark.parametrize(
    ("output", "template_key"),
    [
        (COPILOT_RUNTIME, "tools_copilot"),
        (COPILOT_GENERATED, "tools_copilot"),
        (VSCODE_GENERATED, "tools_vscode"),
    ],
)
def test_generated_tool_contract_matches_template(output: Path, template_key: str) -> None:
    template_tools = _tool_list(_frontmatter(SHARED_TEMPLATE), template_key, SHARED_TEMPLATE)
    output_tools = _tool_list(_frontmatter(output), "tools", output)

    assert output_tools == template_tools


def test_prompt_routes_execution_to_an_execution_agent() -> None:
    claude = CLAUDE_CANONICAL.read_text(encoding="utf-8")
    shared = SHARED_TEMPLATE.read_text(encoding="utf-8")

    assert "This agent cannot invoke skills" in claude
    assert "GitHub and command routing (required)" in claude
    assert "The orchestrator must retrieve" in claude
    assert "GitHub issue, PR, review, and CI context before delegation." in claude
    assert "GitHub and command routing (required)" in shared
    assert "The orchestrator must retrieve" in shared
    assert "Do not claim direct GitHub access" in shared
    assert "Issue #3918 tracks adding structured read-only tooling" not in claude
    assert "Issue #3918 tracks adding structured read-only tooling" not in shared


def test_orchestrator_supplies_analyst_execution_context() -> None:
    for contract in ORCHESTRATOR_CONTRACTS:
        text = contract.read_text(encoding="utf-8")
        assert "### Analyst evidence handoff" in text, contract
        assert "Put the exact output, repository identity, branch, and head SHA" in text, contract
        assert (
            "The analyst is read-only and has no shell, GitHub, or unrestricted web access."
            in text
        ), contract
        assert "external evidence outside the analyst's declared" in text, contract
        assert "worker whose declared manifest includes that" in text, contract
        assert "retrieve the named" in text, contract
        assert "evidence and re-delegate once" in text, contract
        assert "delegate to the analyst agent" not in text, contract


@pytest.mark.parametrize(
    ("tools", "allowed_tools"),
    [
        ([], PLATFORM_ALLOWED_TOOLS),
        (["Read", "Bash"], CLAUDE_ALLOWED_TOOLS),
        (["Read", "Bash(git status:*)"], CLAUDE_ALLOWED_TOOLS),
        (["Read", "Task"], CLAUDE_ALLOWED_TOOLS),
        (["Read", "NotebookEdit"], CLAUDE_ALLOWED_TOOLS),
        (["read", "agent"], PLATFORM_ALLOWED_TOOLS),
        (["read", "cloudmcp-manager/*"], PLATFORM_ALLOWED_TOOLS),
        (["read", "edit"], PLATFORM_ALLOWED_TOOLS),
        (["read", "edit_file"], PLATFORM_ALLOWED_TOOLS),
        (["read", "github/create_or_update_file"], PLATFORM_ALLOWED_TOOLS),
        (["read", "github.vscode-pull-request-github/*"], PLATFORM_ALLOWED_TOOLS),
        (["read", "memory"], PLATFORM_ALLOWED_TOOLS),
        (["read", "perplexity/*"], PLATFORM_ALLOWED_TOOLS),
        (["read", "$toolset:executor"], PLATFORM_ALLOWED_TOOLS),
        (["read", "serena/write_memory"], PLATFORM_ALLOWED_TOOLS),
        (["Read", "mcp__serena__replace_symbol_body"], CLAUDE_ALLOWED_TOOLS),
        (["read", "serena/*"], PLATFORM_ALLOWED_TOOLS),
        (["read", "skill"], PLATFORM_ALLOWED_TOOLS),
        (["read", "web"], PLATFORM_ALLOWED_TOOLS),
    ],
)
def test_read_only_guard_rejects_unsafe_negative_controls(
    tools: list[str], allowed_tools: frozenset[str]
) -> None:
    with pytest.raises(AssertionError):
        _assert_read_only_tools(tools, allowed_tools)


def test_executor_toolset_is_an_unsafe_negative_control() -> None:
    toolsets = yaml.safe_load(TOOLSETS.read_text(encoding="utf-8"))
    assert isinstance(toolsets, dict)
    executor = toolsets["executor"]
    assert isinstance(executor, dict)

    for key in ("tools_copilot", "tools_vscode"):
        tools = executor[key]
        assert isinstance(tools, list)
        with pytest.raises(AssertionError):
            _assert_read_only_tools(tools, PLATFORM_ALLOWED_TOOLS)


def test_reviewed_read_only_allowlists_are_inverted_controls() -> None:
    _assert_read_only_tools(list(CLAUDE_ALLOWED_TOOLS), CLAUDE_ALLOWED_TOOLS)
    _assert_read_only_tools(list(PLATFORM_ALLOWED_TOOLS), PLATFORM_ALLOWED_TOOLS)
