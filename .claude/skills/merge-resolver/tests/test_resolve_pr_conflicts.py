#!/usr/bin/env python3
"""Tests for resolve_pr_conflicts.py.

Covers:
- Security validation (ADR-015 branch names and worktree paths)
- Auto-resolvable file classification
- GitHub runner detection
- Result structure
- Entry point and argument parsing

Exit codes follow ADR-035:
    0 - All tests passed
    1 - One or more tests failed
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts directory to path for imports
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from resolve_pr_conflicts import (  # noqa: E402, I001
    AUTO_RESOLVABLE_PATTERNS,
    build_parser,
    get_safe_worktree_path,
    is_auto_resolvable,
    is_github_runner,
    is_safe_branch_name,
    resolve_pr_conflicts,
)


# ---------------------------------------------------------------------------
# Security Validation - Branch Names (ADR-015)
# ---------------------------------------------------------------------------

class TestSafeBranchName:
    """Test branch name validation for command injection prevention."""

    @pytest.mark.parametrize(
        "branch",
        ["feature/my-branch", "fix/issue-123", "main", "release/v1.0.0"],
    )
    def test_accepts_valid_branch_names(self, branch: str) -> None:
        assert is_safe_branch_name(branch) is True

    def test_rejects_empty_string(self) -> None:
        assert is_safe_branch_name("") is False

    def test_rejects_whitespace_only(self) -> None:
        assert is_safe_branch_name("   ") is False

    def test_rejects_starts_with_hyphen(self) -> None:
        assert is_safe_branch_name("--exec=malicious") is False

    def test_rejects_path_traversal(self) -> None:
        assert is_safe_branch_name("../../../etc/passwd") is False

    def test_rejects_control_characters(self) -> None:
        assert is_safe_branch_name("main\x00secret") is False

    @pytest.mark.parametrize("branch", ["main~1", "main^1", "main:file"])
    def test_rejects_git_special_characters(self, branch: str) -> None:
        assert is_safe_branch_name(branch) is False

    def test_rejects_semicolon_command_injection(self) -> None:
        assert is_safe_branch_name("main;rm -rf /") is False

    def test_rejects_pipe_command_injection(self) -> None:
        assert is_safe_branch_name("main|cat /etc/passwd") is False

    def test_rejects_backtick_command_substitution(self) -> None:
        assert is_safe_branch_name("main`whoami`") is False

    def test_rejects_dollar_sign(self) -> None:
        assert is_safe_branch_name("main$HOME") is False

    def test_rejects_ampersand(self) -> None:
        assert is_safe_branch_name("main&whoami") is False


# ---------------------------------------------------------------------------
# Security Validation - Worktree Path (ADR-015)
# ---------------------------------------------------------------------------

class TestSafeWorktreePath:
    """Test worktree path validation for path traversal prevention."""

    def test_rejects_negative_pr_number(self) -> None:
        with pytest.raises(ValueError, match="Invalid PR number"):
            get_safe_worktree_path("/tmp", -1)

    def test_rejects_zero_pr_number(self) -> None:
        with pytest.raises(ValueError, match="Invalid PR number"):
            get_safe_worktree_path("/tmp", 0)

    def test_constructs_valid_path(self, tmp_path: Path) -> None:
        result = get_safe_worktree_path(str(tmp_path), 123)
        assert result.endswith("ai-agents-pr-123")
        assert str(tmp_path) in result

    def test_rejects_nonexistent_base_path(self) -> None:
        with pytest.raises(FileNotFoundError):
            get_safe_worktree_path("/nonexistent/path", 1)


# ---------------------------------------------------------------------------
# Auto-Resolvable Files
# ---------------------------------------------------------------------------

class TestAutoResolvable:
    """Test auto-resolvable file classification."""

    def test_handoff_md_is_auto_resolvable(self) -> None:
        assert is_auto_resolvable(".agents/HANDOFF.md") is True

    def test_session_files_are_auto_resolvable(self) -> None:
        assert is_auto_resolvable(".agents/sessions/2026-01-01.json") is True

    def test_serena_memories_are_auto_resolvable(self) -> None:
        assert is_auto_resolvable(".serena/memories/test.md") is True

    def test_lock_files_are_auto_resolvable(self) -> None:
        assert is_auto_resolvable("package-lock.json") is True
        assert is_auto_resolvable("pnpm-lock.yaml") is True
        assert is_auto_resolvable("yarn.lock") is True

    def test_source_code_is_not_auto_resolvable(self) -> None:
        assert is_auto_resolvable("src/main.py") is False

    def test_readme_is_not_auto_resolvable(self) -> None:
        assert is_auto_resolvable("README.md") is False

    def test_patterns_list_is_nonempty(self) -> None:
        assert len(AUTO_RESOLVABLE_PATTERNS) > 0


# ---------------------------------------------------------------------------
# GitHub Runner Detection
# ---------------------------------------------------------------------------

class TestGitHubRunner:
    """Test GitHub Actions runner detection."""

    def test_detects_github_runner(self) -> None:
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            assert is_github_runner() is True

    def test_detects_local_environment(self) -> None:
        env = os.environ.copy()
        env.pop("GITHUB_ACTIONS", None)
        with patch.dict(os.environ, env, clear=True):
            assert is_github_runner() is False


# ---------------------------------------------------------------------------
# Result Structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    """Test that resolve_pr_conflicts returns proper structure."""

    def test_unsafe_branch_returns_failure(self) -> None:
        result = resolve_pr_conflicts(
            pr_number=1,
            branch_name="main;rm -rf /",
            target_branch="main",
        )
        assert result["success"] is False
        assert "unsafe branch name" in result["message"]
        assert result["files_resolved"] == []
        assert result["files_blocked"] == []

    def test_unsafe_target_branch_returns_failure(self) -> None:
        result = resolve_pr_conflicts(
            pr_number=1,
            branch_name="feature/ok",
            target_branch="main|hack",
        )
        assert result["success"] is False
        assert "unsafe target branch" in result["message"]


# ---------------------------------------------------------------------------
# Argument Parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    """Test CLI argument parsing."""

    def test_required_args(self) -> None:
        args = build_parser().parse_args([
            "--pr-number", "123",
            "--branch-name", "fix/test",
        ])
        assert args.pr_number == 123
        assert args.branch_name == "fix/test"
        assert args.target_branch == "main"
        assert args.dry_run is False

    def test_all_args(self) -> None:
        args = build_parser().parse_args([
            "--owner", "testowner",
            "--repo", "testrepo",
            "--pr-number", "456",
            "--branch-name", "feat/new",
            "--target-branch", "develop",
            "--worktree-base-path", "/tmp/wt",
            "--dry-run",
        ])
        assert args.owner == "testowner"
        assert args.repo == "testrepo"
        assert args.pr_number == 456
        assert args.target_branch == "develop"
        assert args.worktree_base_path == "/tmp/wt"
        assert args.dry_run is True

    def test_missing_required_args_raises(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args([])
