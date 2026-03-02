#!/usr/bin/env python3
"""Tests for the pre-commit slash commands hook.

Covers: no staged files, staged files pass, staged files fail,
git command failures, validation script failures.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks")
sys.path.insert(0, HOOK_DIR)

import pre_commit_slash_commands  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests for get_staged_slash_commands
# ---------------------------------------------------------------------------


class TestGetStagedSlashCommands:
    """Tests for get_staged_slash_commands function."""

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_matching_files(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                ".claude/commands/foo.md\n"
                ".claude/commands/bar.md\n"
                "src/other.py\n"
            ),
        )
        result = pre_commit_slash_commands.get_staged_slash_commands()
        assert result == [".claude/commands/foo.md", ".claude/commands/bar.md"]

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_empty_on_no_matches(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="src/other.py\n"
        )
        result = pre_commit_slash_commands.get_staged_slash_commands()
        assert result == []

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_empty_on_git_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = pre_commit_slash_commands.get_staged_slash_commands()
        assert result == []

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_empty_on_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")
        result = pre_commit_slash_commands.get_staged_slash_commands()
        assert result == []

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        result = pre_commit_slash_commands.get_staged_slash_commands()
        assert result == []

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_excludes_non_md_files(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=".claude/commands/foo.ps1\n.claude/commands/bar.md\n",
        )
        result = pre_commit_slash_commands.get_staged_slash_commands()
        assert result == [".claude/commands/bar.md"]

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_excludes_nested_non_command_files(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=".claude/other/foo.md\n.claude/commands/bar.md\n",
        )
        result = pre_commit_slash_commands.get_staged_slash_commands()
        assert result == [".claude/commands/bar.md"]


# ---------------------------------------------------------------------------
# Unit tests for validate_file
# ---------------------------------------------------------------------------


class TestValidateFile:
    """Tests for validate_file function."""

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_true_on_pass(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert pre_commit_slash_commands.validate_file(
            "/path/to/validate.ps1", "test.md"
        )

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_false_on_fail(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert not pre_commit_slash_commands.validate_file(
            "/path/to/validate.ps1", "test.md"
        )

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_false_on_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("pwsh not found")
        assert not pre_commit_slash_commands.validate_file(
            "/path/to/validate.ps1", "test.md"
        )

    @patch("pre_commit_slash_commands.subprocess.run")
    def test_returns_false_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="pwsh", timeout=30
        )
        assert not pre_commit_slash_commands.validate_file(
            "/path/to/validate.ps1", "test.md"
        )


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    @patch("pre_commit_slash_commands.get_staged_slash_commands")
    def test_exits_0_when_no_staged_files(self, mock_staged, capsys):
        mock_staged.return_value = []
        with pytest.raises(SystemExit) as exc_info:
            pre_commit_slash_commands.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "[SKIP]" in captured.out

    @patch("pre_commit_slash_commands.validate_file")
    @patch("pre_commit_slash_commands.get_staged_slash_commands")
    def test_exits_0_when_all_pass(self, mock_staged, mock_validate, capsys):
        mock_staged.return_value = [".claude/commands/foo.md"]
        mock_validate.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            pre_commit_slash_commands.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out

    @patch("pre_commit_slash_commands.validate_file")
    @patch("pre_commit_slash_commands.get_staged_slash_commands")
    def test_exits_1_when_any_fail(self, mock_staged, mock_validate, capsys):
        mock_staged.return_value = [
            ".claude/commands/foo.md",
            ".claude/commands/bar.md",
        ]
        mock_validate.side_effect = [True, False]
        with pytest.raises(SystemExit) as exc_info:
            pre_commit_slash_commands.main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.out
        assert "bar.md" in captured.out

    @patch("pre_commit_slash_commands.validate_file")
    @patch("pre_commit_slash_commands.get_staged_slash_commands")
    def test_reports_count_of_staged_files(
        self, mock_staged, mock_validate, capsys
    ):
        mock_staged.return_value = [
            ".claude/commands/a.md",
            ".claude/commands/b.md",
        ]
        mock_validate.return_value = True
        with pytest.raises(SystemExit):
            pre_commit_slash_commands.main()
        captured = capsys.readouterr()
        assert "Found 2 staged slash command(s)" in captured.out
