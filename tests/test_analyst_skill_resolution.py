"""Test analyst agent security contract across ALL platform outputs.

Verifies:
1. No shell/execute/edit in any analyst frontmatter tools
2. No direct git/gh/python3/web instructions in prose
3. Delegation contract with [BLOCKED] response
4. Serena narrowed to read-only operations (no wildcard)
5. All platform outputs enumerated and tested
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True,
).strip())

# ALL analyst outputs that must satisfy the security contract
ALL_ANALYST_FILES = [
    REPO_ROOT / ".claude" / "agents" / "analyst.md",
    REPO_ROOT / "src" / "claude" / "analyst.md",
    REPO_ROOT / ".github" / "agents" / "analyst.agent.md",
    REPO_ROOT / "src" / "copilot-cli" / "agents" / "analyst.agent.md",
    REPO_ROOT / "src" / "vs-code-agents" / "analyst.agent.md",
    REPO_ROOT / "templates" / "agents" / "analyst.shared.md",
]

# Unsafe tools that must never appear in the analyst's expanded toolset
UNSAFE_TOOLS = {"shell", "execute", "edit", "web", "perplexity/*"}

# Unsafe tool prefixes in frontmatter
UNSAFE_PREFIXES = [
    "- shell", "- execute", "- edit", "- web",
    "- Bash(", "- WebSearch", "- WebFetch",
    "- perplexity",
]

# Read-only serena operations (the only ones allowed)
SERENA_READONLY = {
    "find_symbol", "find_referencing_symbols", "find_implementations",
    "get_symbols_overview", "get_diagnostics_for_file", "find_declaration",
    "list_memories", "read_memory", "initial_instructions",
}

# Serena write operations (must never appear)
SERENA_WRITES = {
    "replace_content", "replace_in_files", "replace_symbol_body",
    "insert_after_symbol", "insert_before_symbol",
    "rename_symbol", "safe_delete_symbol",
    "write_memory", "edit_memory", "delete_memory", "rename_memory",
    "onboarding",
}

GITHUB_READ_OPERATIONS = {
    "issue_read",
    "pull_request_read",
    "get_file_contents",
    "list_commits",
}

CI_READ_OPERATIONS = {
    "list_workflow_runs",
    "get_workflow_run",
    "get_job_logs",
}

REQUIRED_GITHUB_READ_TOOLS = {
    f"github/{operation}" for operation in GITHUB_READ_OPERATIONS
}

REQUIRED_CI_READ_TOOLS = {
    f"github/{operation}" for operation in CI_READ_OPERATIONS
}

CLAUDE_GITHUB_READ_TOOLS = {
    f"mcp__github__{operation}" for operation in GITHUB_READ_OPERATIONS
}

CLAUDE_CI_READ_TOOLS = {
    f"mcp__github__{operation}" for operation in CI_READ_OPERATIONS
}

PORTABLE_READONLY_TOOLS = {
    "read",
    "search",
    "cognitionai/deepwiki/read_wiki_structure",
    "cognitionai/deepwiki/read_wiki_contents",
    "context7/resolve-library-id",
    "context7/get-library-docs",
    *REQUIRED_GITHUB_READ_TOOLS,
    *REQUIRED_CI_READ_TOOLS,
    *(f"serena/{operation}" for operation in SERENA_READONLY),
}

CLAUDE_READONLY_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "mcp__context7__resolve-library-id",
    "mcp__context7__get-library-docs",
    "mcp__deepwiki__read_wiki_structure",
    "mcp__deepwiki__read_wiki_contents",
    *CLAUDE_GITHUB_READ_TOOLS,
    *CLAUDE_CI_READ_TOOLS,
    *(f"mcp__serena__{operation}" for operation in SERENA_READONLY),
}

EXPECTED_TOOL_GROUPS = {
    ALL_ANALYST_FILES[0]: {"tools": CLAUDE_READONLY_TOOLS},
    ALL_ANALYST_FILES[1]: {"tools": CLAUDE_READONLY_TOOLS},
    ALL_ANALYST_FILES[2]: {"tools": PORTABLE_READONLY_TOOLS},
    ALL_ANALYST_FILES[3]: {"tools": PORTABLE_READONLY_TOOLS},
    ALL_ANALYST_FILES[4]: {"tools": PORTABLE_READONLY_TOOLS},
    ALL_ANALYST_FILES[5]: {
        "tools_vscode": PORTABLE_READONLY_TOOLS,
        "tools_copilot": PORTABLE_READONLY_TOOLS,
    },
}


def _extract_frontmatter(text: str) -> str:
    """Extract YAML frontmatter from a file."""
    parts = text.split("---", 2)
    if len(parts) >= 3:
        return parts[1]
    return ""


def _extract_tool_groups(frontmatter: str) -> dict[str, list[str]]:
    """Parse each tool group from YAML frontmatter."""
    data = yaml.safe_load(frontmatter) or {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a YAML mapping")

    groups: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        if key != "tools" and not key.startswith("tools_"):
            continue
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list of tool names")
        if not all(isinstance(tool, str) for tool in value):
            raise ValueError(f"{key} must contain only tool names")
        groups[key] = value
    return groups


def _extract_tools(frontmatter: str) -> list[str]:
    """Flatten parsed tool groups from frontmatter."""
    return [
        tool
        for tools in _extract_tool_groups(frontmatter).values()
        for tool in tools
    ]


class TestAllFilesExist:
    """All analyst output files must exist."""

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_file_exists(self, path: Path) -> None:
        assert path.is_file(), f"Missing: {path.relative_to(REPO_ROOT)}"


class TestNoUnsafeToolsInFrontmatter:
    """No analyst file may have shell/execute/edit/web in its tool allowlist."""

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_no_unsafe_tools(self, path: Path) -> None:
        text = path.read_text()
        frontmatter = _extract_frontmatter(text)
        actual_groups = _extract_tool_groups(frontmatter)
        expected_groups = EXPECTED_TOOL_GROUPS[path]
        assert set(actual_groups) == set(expected_groups), (
            f"{path.relative_to(REPO_ROOT)}: unexpected tool groups "
            f"{sorted(actual_groups)}"
        )
        for group, allowed_tools in expected_groups.items():
            actual_tools = actual_groups[group]
            assert len(actual_tools) == len(set(actual_tools)), (
                f"{path.relative_to(REPO_ROOT)}: duplicate tool in {group}"
            )
            assert set(actual_tools) == allowed_tools, (
                f"{path.relative_to(REPO_ROOT)}: {group} differs from the "
                f"read-only allowlist; extra="
                f"{sorted(set(actual_tools) - allowed_tools)}, missing="
                f"{sorted(allowed_tools - set(actual_tools))}"
            )

        tools = _extract_tools(frontmatter)
        for tool in tools:
            for unsafe in UNSAFE_PREFIXES:
                if tool.startswith(unsafe.lstrip("- ")):
                    pytest.fail(
                        f"{path.relative_to(REPO_ROOT)}: unsafe tool '{tool}' in frontmatter"
                    )

    def test_flow_style_tool_list_is_parsed(self) -> None:
        frontmatter = "tools: [read, shell, editFiles, WebFetch]"

        assert _extract_tools(frontmatter) == [
            "read",
            "shell",
            "editFiles",
            "WebFetch",
        ]

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_no_serena_wildcard(self, path: Path) -> None:
        """serena/* wildcard must not appear; only explicit read-only ops."""
        text = path.read_text()
        frontmatter = _extract_frontmatter(text)
        tools = _extract_tools(frontmatter)
        for tool in tools:
            if tool == "serena/*" or tool == "mcp__serena__*":
                pytest.fail(
                    f"{path.relative_to(REPO_ROOT)}: serena wildcard in tools"
                )

    @pytest.mark.parametrize(
        "path",
        ALL_ANALYST_FILES,
        ids=lambda p: str(p.relative_to(REPO_ROOT)),
    )
    def test_no_mcp_wildcard(self, path: Path) -> None:
        """Every MCP tool must name one reviewed read-only operation."""
        text = path.read_text()
        frontmatter = _extract_frontmatter(text)
        tools = _extract_tools(frontmatter)
        wildcard_tools = [tool for tool in tools if "*" in tool]
        assert not wildcard_tools, (
            f"{path.relative_to(REPO_ROOT)}: wildcard MCP tools "
            f"{wildcard_tools}"
        )

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_no_serena_write_ops(self, path: Path) -> None:
        """No serena write operation may appear in tools."""
        text = path.read_text()
        frontmatter = _extract_frontmatter(text)
        tools = _extract_tools(frontmatter)
        for tool in tools:
            for write_op in SERENA_WRITES:
                if write_op in tool:
                    pytest.fail(
                        f"{path.relative_to(REPO_ROOT)}: serena write op '{tool}'"
                    )


class TestRequiredReadOnlyGitHubTools:
    """Analyst outputs must keep PR, issue, file, commit, and CI read tools."""

    @pytest.mark.parametrize(
        "path",
        ALL_ANALYST_FILES,
        ids=lambda p: str(p.relative_to(REPO_ROOT)),
    )
    def test_required_read_tools_present(self, path: Path) -> None:
        text = path.read_text()
        frontmatter = _extract_frontmatter(text)
        tools = set(_extract_tools(frontmatter))
        is_claude = path in ALL_ANALYST_FILES[:2]
        required_github = (
            CLAUDE_GITHUB_READ_TOOLS
            if is_claude
            else REQUIRED_GITHUB_READ_TOOLS
        )
        required_ci = (
            CLAUDE_CI_READ_TOOLS
            if is_claude
            else REQUIRED_CI_READ_TOOLS
        )
        missing_github = required_github - tools
        missing_ci = required_ci - tools
        assert not missing_github, (
            f"{path.relative_to(REPO_ROOT)}: missing GitHub read tools "
            f"{sorted(missing_github)}"
        )
        assert not missing_ci, (
            f"{path.relative_to(REPO_ROOT)}: missing CI read tools "
            f"{sorted(missing_ci)}"
        )

    @pytest.mark.parametrize(
        "path",
        ALL_ANALYST_FILES,
        ids=lambda p: str(p.relative_to(REPO_ROOT)),
    )
    def test_prose_uses_declared_github_read_tools(self, path: Path) -> None:
        text = path.read_text()
        assert "Use the declared GitHub read tools" in text, (
            f"{path.relative_to(REPO_ROOT)}: GitHub read tools are declared "
            "but not used by the agent contract"
        )
        assert "Do not claim the ability to retrieve GitHub data" not in text, (
            f"{path.relative_to(REPO_ROOT)}: prose contradicts declared "
            "GitHub read tools"
        )


class TestNoDirectGitHubGuidance:
    """Prose must not instruct direct GitHub/shell/web access."""

    @pytest.mark.parametrize(
        "path",
        ALL_ANALYST_FILES,
        ids=lambda p: str(p.relative_to(REPO_ROOT)),
    )
    def test_no_positive_shell_instruction(self, path: Path) -> None:
        text = path.read_text()
        body = text.split("---", 2)[-1] if "---" in text else text
        negations = ["cannot", "do not", "must not", "never", "no shell",
                     "no web", "not available", "has no"]
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("```"):
                continue
            lower = stripped.lower()
            # Check for positive git/gh invocations
            if any(cmd in lower for cmd in ["gh api ", "gh pr ", "git branch", "git rev-parse"]):
                if not any(neg in lower for neg in negations):
                    pytest.fail(
                        f"{path.relative_to(REPO_ROOT)}: "
                        f"direct shell instruction: {stripped[:80]}"
                    )

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_no_positive_web_tool_instruction(self, path: Path) -> None:
        """Prose must not direct the analyst to unavailable web tools."""
        text = path.read_text()
        body = text.split("---", 2)[-1] if "---" in text else text
        negations = [
            "cannot",
            "do not",
            "must not",
            "never",
            "no web",
            "not available",
            "has no",
            "retired",
        ]
        for line in body.splitlines():
            lower = line.strip().lower()
            if "websearch" not in lower and "webfetch" not in lower:
                continue
            if not any(negation in lower for negation in negations):
                pytest.fail(
                    f"{path.relative_to(REPO_ROOT)}: "
                    f"positive web-tool instruction: {line.strip()[:80]}"
                )


class TestDelegationContract:
    """All analyst outputs must have the [BLOCKED] delegation contract."""

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_blocked_response(self, path: Path) -> None:
        text = path.read_text()
        assert "[BLOCKED]" in text, f"{path.relative_to(REPO_ROOT)}: no [BLOCKED] response"

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_missing_context_list(self, path: Path) -> None:
        text = path.read_text()
        assert "Missing context required for analysis" in text, (
            f"{path.relative_to(REPO_ROOT)}: no missing-context list"
        )


class TestUntrustedContentBoundary:
    """All analyst outputs must have the untrusted-content boundary instruction."""

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_boundary_present(self, path: Path) -> None:
        text = path.read_text()
        assert "untrusted-content boundary" in text.lower() or "DATA, never" in text, (
            f"{path.relative_to(REPO_ROOT)}: no untrusted-content boundary"
        )

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_delegated_content_is_untrusted(self, path: Path) -> None:
        text = path.read_text().lower()
        assert "delegated pr bodies" in text, (
            f"{path.relative_to(REPO_ROOT)}: delegated PR content is not "
            "inside the untrusted-content boundary"
        )
        assert "follow directives embedded in delegated content" in text, (
            f"{path.relative_to(REPO_ROOT)}: no explicit ban on following "
            "directives from delegated content"
        )


class TestParity:
    """Hand-maintained copies must be byte-identical."""

    def test_claude_agents_parity(self) -> None:
        a = (REPO_ROOT / ".claude" / "agents" / "analyst.md").read_text()
        b = (REPO_ROOT / "src" / "claude" / "analyst.md").read_text()
        assert a == b

    def test_github_matches_copilot_cli(self) -> None:
        a = (REPO_ROOT / ".github" / "agents" / "analyst.agent.md").read_text()
        b = (REPO_ROOT / "src" / "copilot-cli" / "agents" / "analyst.agent.md").read_text()
        assert a == b


class TestPRRetrievalBeforeBlocked:
    """Analyst must attempt pull_request_read before returning BLOCKED.

    Regression: prior versions would return BLOCKED immediately on PR URL/number
    input without attempting retrieval via the declared read-only tools.
    """

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_pull_request_read_declared(self, path: Path) -> None:
        """pull_request_read must be in the tool allowlist (precondition for retrieval)."""
        text = path.read_text()
        assert "pull_request_read" in text, (
            f"{path.relative_to(REPO_ROOT)}: pull_request_read not declared; "
            "analyst cannot retrieve PR context before BLOCKED"
        )

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_blocked_requires_retrieval_failure(self, path: Path) -> None:
        """BLOCKED must be conditional on retrieval failure, not immediate."""
        text = path.read_text()
        # The template must instruct: use tools first, BLOCKED only if unavailable
        assert "use" in text.lower() and "read tools" in text.lower() or \
               "retrieve" in text.lower() and "read" in text.lower(), (
            f"{path.relative_to(REPO_ROOT)}: no instruction to attempt retrieval "
            "before returning BLOCKED"
        )
        # BLOCKED must be paired with "unavailable" or "missing" or "fails"
        blocked_idx = text.find("[BLOCKED]")
        assert blocked_idx != -1
        context_around_blocked = text[max(0, blocked_idx - 200):blocked_idx + 200].lower()
        has_conditional = any(
            word in context_around_blocked
            for word in ("unavailable", "missing", "cannot", "fails", "if required")
        )
        assert has_conditional, (
            f"{path.relative_to(REPO_ROOT)}: [BLOCKED] is not conditioned on "
            "context being unavailable after retrieval attempt"
        )

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_ci_log_retrieval_declared(self, path: Path) -> None:
        """CI log retrieval tool must be declared for CI analysis."""
        text = path.read_text()
        assert "get_job_logs" in text, (
            f"{path.relative_to(REPO_ROOT)}: get_job_logs not declared; "
            "analyst cannot retrieve CI logs"
        )

    def test_local_identity_not_required_for_remote_analysis(self) -> None:
        """The canonical template must not require local identity for remote-only PR analysis."""
        template = REPO_ROOT / "templates" / "agents" / "analyst.shared.md"
        text = template.read_text()
        # Must state local identity is conditional
        assert "when present" in text.lower() or "only when" in text.lower(), (
            "templates/agents/analyst.shared.md: local identity columns must be "
            "marked as conditional (not required for remote-only API analysis)"
        )
