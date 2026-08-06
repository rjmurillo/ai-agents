"""Test analyst agent security contract across ALL platform outputs.

Verifies:
1. No shell/execute/edit in any analyst frontmatter tools
2. No direct git/gh/python3/web instructions in prose
3. Delegation contract with [BLOCKED] response
4. Serena narrowed to read-only operations (no wildcard)
5. All platform outputs enumerated and tested
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

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


def _extract_frontmatter(text: str) -> str:
    """Extract YAML frontmatter from a file."""
    parts = text.split("---", 2)
    if len(parts) >= 3:
        return parts[1]
    return ""


def _extract_tools(frontmatter: str) -> list[str]:
    """Extract tool lines from frontmatter."""
    tools = []
    in_tools = False
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if stripped.startswith("tools") and ":" in stripped:
            in_tools = True
            continue
        if in_tools:
            if stripped.startswith("- "):
                tools.append(stripped[2:])
            elif stripped and not stripped.startswith("#"):
                in_tools = False
    return tools


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
        tools = _extract_tools(frontmatter)
        for tool in tools:
            for unsafe in UNSAFE_PREFIXES:
                if tool.startswith(unsafe.lstrip("- ")):
                    pytest.fail(
                        f"{path.relative_to(REPO_ROOT)}: unsafe tool '{tool}' in frontmatter"
                    )

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


class TestNoDirectGitHubGuidance:
    """Prose must not instruct direct GitHub/shell/web access."""

    @pytest.mark.parametrize("path", ALL_ANALYST_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
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
                    pytest.fail(f"{path.relative_to(REPO_ROOT)}: direct shell instruction: {stripped[:80]}")


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
