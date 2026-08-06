"""Test analyst agent security contract: no shell execution, delegation-only GitHub access.

Verifies:
1. No Bash wildcard or shell tool in the allowlist
2. No direct gh/git/python3 guidance in prose
3. Delegation contract requires supplied context
4. Missing context produces [BLOCKED] response in prose
5. Parity between plugin roots
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True,
).strip())

ANALYST_MD = REPO_ROOT / ".claude" / "agents" / "analyst.md"
ANALYST_SRC = REPO_ROOT / "src" / "claude" / "analyst.md"


class TestNoBashWildcard:
    """The analyst must have no Bash tool permission of any kind."""

    def test_no_bash_in_tools_frontmatter(self) -> None:
        text = ANALYST_MD.read_text()
        # Extract frontmatter
        parts = text.split("---", 2)
        assert len(parts) >= 3, "No YAML frontmatter found"
        frontmatter = parts[1]
        for line in frontmatter.splitlines():
            stripped = line.strip()
            if stripped.startswith("- Bash"):
                pytest.fail(f"Bash tool found in frontmatter: {stripped}")

    def test_no_python3_in_tools_frontmatter(self) -> None:
        text = ANALYST_MD.read_text()
        parts = text.split("---", 2)
        frontmatter = parts[1]
        assert "python3" not in frontmatter

    def test_no_git_tool_in_frontmatter(self) -> None:
        text = ANALYST_MD.read_text()
        parts = text.split("---", 2)
        frontmatter = parts[1]
        # "git" could appear in description, so check tool lines only
        for line in frontmatter.splitlines():
            stripped = line.strip()
            if stripped.startswith("- Bash(git"):
                pytest.fail(f"git tool found: {stripped}")

    def test_no_gh_tool_in_frontmatter(self) -> None:
        text = ANALYST_MD.read_text()
        parts = text.split("---", 2)
        frontmatter = parts[1]
        for line in frontmatter.splitlines():
            stripped = line.strip()
            if stripped.startswith("- Bash(gh"):
                pytest.fail(f"gh tool found: {stripped}")


class TestNoDirectGitHubGuidance:
    """Prose must not instruct the analyst to run shell commands."""

    def test_no_gh_api_instruction(self) -> None:
        text = ANALYST_MD.read_text()
        # Split off frontmatter
        body = text.split("---", 2)[2]
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Allow negations like "cannot run" or "do not"
            if "gh api" in stripped.lower() or "gh pr" in stripped.lower():
                if any(neg in stripped.lower() for neg in
                       ["cannot", "do not", "must not", "never", "no shell"]):
                    continue
                pytest.fail(f"Direct gh instruction found: {stripped}")

    def test_no_python3_invocation_instruction(self) -> None:
        text = ANALYST_MD.read_text()
        body = text.split("---", 2)[2]
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "python3 " in stripped and "$" in stripped:
                # This is a command invocation pattern
                if any(neg in stripped.lower() for neg in
                       ["cannot", "do not", "must not", "never"]):
                    continue
                pytest.fail(f"python3 invocation instruction: {stripped}")

    def test_no_bundled_script_reference(self) -> None:
        text = ANALYST_MD.read_text()
        assert "github_query.py" not in text
        assert "CLAUDE_PLUGIN_ROOT/scripts" not in text


class TestDelegationContract:
    """Analyst must declare that GitHub context comes from orchestrator."""

    def test_blocked_response_documented(self) -> None:
        text = ANALYST_MD.read_text()
        assert "[BLOCKED]" in text

    def test_missing_context_list_pattern(self) -> None:
        text = ANALYST_MD.read_text()
        assert "Missing context required for analysis" in text

    def test_orchestrator_delegation_mentioned(self) -> None:
        text = ANALYST_MD.read_text()
        assert "orchestrator" in text.lower() or "delegation prompt" in text.lower()

    def test_no_direct_retrieval_claim(self) -> None:
        """Must not claim ability to fetch GitHub data directly."""
        text = ANALYST_MD.read_text()
        body = text.split("---", 2)[2]
        assert "fetch pr" not in body.lower() or "cannot" in body.lower()
        # Should not have a "how to query GitHub" section
        assert "### GitHub queries" not in body


class TestParity:
    """Both copies must be byte-identical."""

    def test_md_parity(self) -> None:
        assert ANALYST_MD.read_text() == ANALYST_SRC.read_text()

    def test_no_bundled_scripts_exist(self) -> None:
        """The github_query.py script must not exist in either root."""
        assert not (REPO_ROOT / ".claude" / "scripts" / "github_query.py").exists()
        assert not (REPO_ROOT / "src" / "claude" / "scripts" / "github_query.py").exists()
