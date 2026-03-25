#!/usr/bin/env python3
"""Tests for resolve_pr_conflicts module."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py")
is_safe_branch_name = mod.is_safe_branch_name
get_safe_worktree_path = mod.get_safe_worktree_path
is_auto_resolvable = mod.is_auto_resolvable
is_github_runner = mod.is_github_runner
get_repo_info = mod.get_repo_info
resolve_pr_conflicts = mod.resolve_pr_conflicts
AUTO_RESOLVABLE_PATTERNS = mod.AUTO_RESOLVABLE_PATTERNS


class TestIsSafeBranchName:
    """Tests for branch name validation (ADR-015)."""

    def test_valid_branch_names(self) -> None:
        assert is_safe_branch_name("feature/my-branch") is True
        assert is_safe_branch_name("fix/123-bug") is True
        assert is_safe_branch_name("main") is True

    def test_rejects_empty(self) -> None:
        assert is_safe_branch_name("") is False
        assert is_safe_branch_name("   ") is False

    def test_rejects_hyphen_prefix(self) -> None:
        assert is_safe_branch_name("-bad-branch") is False

    def test_rejects_path_traversal(self) -> None:
        assert is_safe_branch_name("../evil") is False
        assert is_safe_branch_name("a/../b") is False

    def test_rejects_control_characters(self) -> None:
        assert is_safe_branch_name("branch\x00name") is False
        assert is_safe_branch_name("branch\x1fname") is False

    def test_rejects_git_special_chars(self) -> None:
        assert is_safe_branch_name("branch~1") is False
        assert is_safe_branch_name("branch^2") is False
        assert is_safe_branch_name("branch:ref") is False
        assert is_safe_branch_name("branch*glob") is False

    def test_rejects_shell_metacharacters(self) -> None:
        assert is_safe_branch_name("branch;rm -rf") is False
        assert is_safe_branch_name("branch|pipe") is False
        assert is_safe_branch_name("branch$(cmd)") is False
        assert is_safe_branch_name("branch`cmd`") is False


class TestGetSafeWorktreePath:
    """Tests for worktree path validation (ADR-015)."""

    def test_constructs_valid_path(self, tmp_path: Path) -> None:
        result = get_safe_worktree_path(str(tmp_path), 123)
        assert "ai-agents-pr-123" in result
        assert str(tmp_path) in result

    def test_rejects_negative_pr_number(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid PR number"):
            get_safe_worktree_path(str(tmp_path), -1)

    def test_rejects_zero_pr_number(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid PR number"):
            get_safe_worktree_path(str(tmp_path), 0)


class TestIsAutoResolvable:
    """Tests for auto-resolvable file detection."""

    def test_handoff_is_resolvable(self) -> None:
        assert is_auto_resolvable(".agents/HANDOFF.md") is True

    def test_session_files_resolvable(self) -> None:
        assert is_auto_resolvable(".agents/sessions/2025-01-01.json") is True

    def test_serena_memories_resolvable(self) -> None:
        assert is_auto_resolvable(".serena/memories/test.md") is True

    def test_lock_files_resolvable(self) -> None:
        assert is_auto_resolvable("package-lock.json") is True
        assert is_auto_resolvable("pnpm-lock.yaml") is True
        assert is_auto_resolvable("yarn.lock") is True

    def test_source_code_not_resolvable(self) -> None:
        assert is_auto_resolvable("src/main.py") is False
        assert is_auto_resolvable("app/controllers/main.rb") is False

    def test_skill_files_resolvable(self) -> None:
        assert is_auto_resolvable(".claude/skills/test/SKILL.md") is True


class TestIsGithubRunner:
    """Tests for GitHub Actions detection."""

    def test_detects_github_actions(self) -> None:
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            assert is_github_runner() is True

    def test_returns_false_locally(self) -> None:
        env = os.environ.copy()
        env.pop("GITHUB_ACTIONS", None)
        with patch.dict(os.environ, env, clear=True):
            assert is_github_runner() is False


class TestResolvePrConflicts:
    """Tests for resolve_pr_conflicts function."""

    def test_rejects_unsafe_branch_name(self) -> None:
        result = resolve_pr_conflicts(
            pr_number=1,
            branch_name="-evil-branch",
            target_branch="main",
        )
        assert result["success"] is False
        assert "unsafe branch name" in result["message"]

    def test_rejects_unsafe_target_branch(self) -> None:
        result = resolve_pr_conflicts(
            pr_number=1,
            branch_name="good-branch",
            target_branch="main;rm -rf /",
        )
        assert result["success"] is False
        assert "unsafe target branch" in result["message"]

    def test_result_structure(self) -> None:
        result = resolve_pr_conflicts(
            pr_number=1,
            branch_name="-evil-branch",
            target_branch="main",
        )
        assert "success" in result
        assert "message" in result
        assert "files_resolved" in result
        assert "files_blocked" in result


class TestGetRepoInfo:
    """Tests for get_repo_info function."""

    def _make_proc(self, stdout: str = "", returncode: int = 0) -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = ""
        return proc

    def test_parses_https_remote(self) -> None:
        with patch("subprocess.run", return_value=self._make_proc("https://github.com/owner/repo.git")):
            result = get_repo_info()
        assert result.owner == "owner"
        assert result.repo == "repo"

    def test_parses_ssh_remote(self) -> None:
        with patch("subprocess.run", return_value=self._make_proc("git@github.com:owner/repo.git")):
            result = get_repo_info()
        assert result.owner == "owner"
        assert result.repo == "repo"

    def test_raises_for_non_github(self) -> None:
        with patch("subprocess.run", return_value=self._make_proc("https://gitlab.com/owner/repo.git")):
            with pytest.raises(RuntimeError, match="Could not parse"):
                get_repo_info()

    def test_raises_for_no_remote(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            with pytest.raises(RuntimeError, match="Could not determine git remote origin"):
                get_repo_info()
