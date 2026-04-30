#!/usr/bin/env python3
"""Tests for validate_slash_command.py.

Covers all 5 validation categories:
1. Frontmatter validation
2. Argument validation
3. Security validation
4. Length validation
5. Lint validation (structural tests only)

Exit codes follow ADR-035:
    0 - All tests passed
    1 - One or more tests failed
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to path for imports
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from validate_slash_command import validate_slash_command  # noqa: E402, I001


# ---------------------------------------------------------------------------
# Frontmatter Validation
# ---------------------------------------------------------------------------

class TestFrontmatterValidation:
    """Test frontmatter parsing and validation."""

    def test_fails_when_frontmatter_missing(self, tmp_path: Path) -> None:
        f = tmp_path / "no-frontmatter.md"
        f.write_text("# Command without frontmatter\n")
        violations, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking > 0
        assert any("Missing YAML frontmatter" in v for v in violations)

    def test_fails_when_description_missing(self, tmp_path: Path) -> None:
        f = tmp_path / "no-description.md"
        f.write_text("---\nargument-hint: <arg>\n---\nCommand\n")
        violations, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking > 0
        assert any("Missing 'description'" in v for v in violations)

    def test_passes_with_trigger_description(self, tmp_path: Path) -> None:
        f = tmp_path / "valid-trigger.md"
        f.write_text(
            "---\n"
            "description: Use when Claude needs to analyze code patterns\n"
            "---\nAnalyze the codebase\n"
        )
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0

    def test_passes_with_generate_description(self, tmp_path: Path) -> None:
        f = tmp_path / "valid-generate.md"
        f.write_text(
            "---\ndescription: Generate a summary report\n---\nContent\n"
        )
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0

    def test_passes_with_research_description(self, tmp_path: Path) -> None:
        f = tmp_path / "valid-research.md"
        f.write_text(
            "---\ndescription: Research best practices\n---\nContent\n"
        )
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0

    def test_warns_with_non_trigger_description(self, tmp_path: Path) -> None:
        f = tmp_path / "non-trigger.md"
        f.write_text(
            "---\ndescription: This is a command for testing\n---\nContent\n"
        )
        violations, blocking, warning = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0
        assert warning > 0
        assert any("Description should start with action verb" in v for v in violations)


# ---------------------------------------------------------------------------
# Argument Validation
# ---------------------------------------------------------------------------

class TestArgumentValidation:
    """Test argument consistency checks."""

    def test_fails_when_arguments_used_without_hint(self, tmp_path: Path) -> None:
        f = tmp_path / "missing-hint.md"
        f.write_text(
            "---\ndescription: Use when testing arguments\n---\n"
            "Process $ARGUMENTS\n"
        )
        violations, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking > 0
        assert any("uses arguments but no 'argument-hint'" in v for v in violations)

    def test_passes_when_hint_matches_usage(self, tmp_path: Path) -> None:
        f = tmp_path / "valid-args.md"
        f.write_text(
            "---\n"
            "description: Use when processing input\n"
            "argument-hint: <input-data>\n"
            "---\nProcess $ARGUMENTS\n"
        )
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0

    def test_fails_with_positional_args_without_hint(self, tmp_path: Path) -> None:
        f = tmp_path / "positional.md"
        f.write_text(
            "---\ndescription: Use when testing positional args\n---\n"
            "First: $1\nSecond: $2\n"
        )
        violations, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking > 0

    def test_warns_when_hint_exists_but_unused(self, tmp_path: Path) -> None:
        f = tmp_path / "unused-hint.md"
        f.write_text(
            "---\n"
            "description: Use when testing unused hints\n"
            "argument-hint: <unused>\n"
            "---\nNo arguments used here\n"
        )
        violations, _, warning = validate_slash_command(str(f), skip_lint=True)
        assert warning > 0
        assert any("argument-hint" in v and "doesn't use arguments" in v for v in violations)


# ---------------------------------------------------------------------------
# Security Validation
# ---------------------------------------------------------------------------

class TestSecurityValidation:
    """Test security constraint enforcement."""

    def test_fails_when_bash_has_no_allowed_tools(self, tmp_path: Path) -> None:
        f = tmp_path / "bash-no-tools.md"
        f.write_text(
            "---\ndescription: Use when running git commands\n---\n"
            "Execute: !git status\n"
        )
        violations, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking > 0
        assert any("bash execution" in v and "allowed-tools" in v for v in violations)

    def test_fails_with_overly_permissive_wildcard(self, tmp_path: Path) -> None:
        f = tmp_path / "bad-wildcard.md"
        f.write_text(
            "---\n"
            "description: Use when running commands\n"
            "allowed-tools: [*]\n"
            "---\nExecute: !git status\n"
        )
        violations, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking > 0
        assert any("overly permissive wildcard" in v for v in violations)

    def test_passes_with_scoped_mcp_wildcard(self, tmp_path: Path) -> None:
        f = tmp_path / "scoped-mcp.md"
        f.write_text(
            "---\n"
            "description: Use when using MCP tools\n"
            "allowed-tools: [mcp__*]\n"
            "---\nExecute: !mcp__serena__find_symbol\n"
        )
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0

    def test_passes_with_scoped_serena_wildcard(self, tmp_path: Path) -> None:
        f = tmp_path / "scoped-serena.md"
        f.write_text(
            "---\n"
            "description: Use when using Serena tools\n"
            "allowed-tools: [mcp__serena__*]\n"
            "---\nExecute: !mcp__serena__find_symbol\n"
        )
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0

    def test_passes_with_explicit_tool_list(self, tmp_path: Path) -> None:
        f = tmp_path / "explicit-tools.md"
        f.write_text(
            "---\n"
            "description: Use when running specific tools\n"
            "allowed-tools: [Bash, Read, Write]\n"
            "---\nExecute: !git status\n"
        )
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0


# ---------------------------------------------------------------------------
# Length Validation
# ---------------------------------------------------------------------------

class TestLengthValidation:
    """Test file length warnings."""

    def test_warns_when_over_200_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "long-file.md"
        header = "---\ndescription: Use when testing long files\n---\n"
        lines = "\n".join(f"Line {i}" for i in range(250))
        f.write_text(header + lines)
        violations, _, warning = validate_slash_command(str(f), skip_lint=True)
        assert warning > 0
        assert any(">200" in v and "Consider converting" in v for v in violations)

    def test_no_warning_under_200_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "normal-file.md"
        f.write_text(
            "---\ndescription: Use when testing normal files\n---\n"
            "Normal content\n"
        )
        violations, _, _ = validate_slash_command(str(f), skip_lint=True)
        assert not any(">200" in v for v in violations)


# ---------------------------------------------------------------------------
# Exit Code Behavior
# ---------------------------------------------------------------------------

class TestExitCodes:
    """Test exit code behavior."""

    def test_passes_valid_command(self, tmp_path: Path) -> None:
        f = tmp_path / "valid.md"
        f.write_text(
            "---\ndescription: Use when testing valid commands\n---\n"
            "Valid command content\n"
        )
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0

    def test_fails_blocking_violation(self, tmp_path: Path) -> None:
        f = tmp_path / "blocking.md"
        f.write_text("No frontmatter at all\n")
        _, blocking, _ = validate_slash_command(str(f), skip_lint=True)
        assert blocking > 0

    def test_passes_warning_only(self, tmp_path: Path) -> None:
        f = tmp_path / "warning-only.md"
        f.write_text(
            "---\n"
            "description: This description does not start with action verb\n"
            "---\nWarning only content\n"
        )
        _, blocking, warning = validate_slash_command(str(f), skip_lint=True)
        assert blocking == 0
        assert warning > 0

    def test_fails_for_missing_file(self) -> None:
        violations, blocking, _ = validate_slash_command(
            "/nonexistent/file.md", skip_lint=True,
        )
        assert blocking > 0
