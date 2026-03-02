#!/usr/bin/env python3
"""Tests for the branch protection guard hook.

Covers all branches: allow on feature branch, block on main/master,
git failures, missing input, invalid JSON, tty input, env fallback.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add hook directory to path for direct imports
HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse")
sys.path.insert(0, HOOK_DIR)

import branch_protection_guard  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests for get_working_directory
# ---------------------------------------------------------------------------


class TestGetWorkingDirectory:
    """Tests for get_working_directory function."""

    def test_uses_cwd_from_hook_input(self):
        result = branch_protection_guard.get_working_directory(
            {"cwd": "/some/path"}
        )
        assert result == "/some/path"

    def test_strips_whitespace_from_cwd(self):
        result = branch_protection_guard.get_working_directory(
            {"cwd": "  /some/path  "}
        )
        assert result == "/some/path"

    def test_falls_back_to_env_var(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/env/path")
        result = branch_protection_guard.get_working_directory({"cwd": ""})
        assert result == "/env/path"

    def test_falls_back_to_env_var_when_cwd_missing(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/env/path")
        result = branch_protection_guard.get_working_directory({})
        assert result == "/env/path"

    def test_falls_back_to_os_getcwd(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = branch_protection_guard.get_working_directory({"cwd": ""})
        assert result  # Should return current working directory

    def test_ignores_whitespace_only_cwd(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/env/path")
        result = branch_protection_guard.get_working_directory(
            {"cwd": "   "}
        )
        assert result == "/env/path"

    def test_ignores_whitespace_only_env(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "   ")
        result = branch_protection_guard.get_working_directory({"cwd": ""})
        # Falls through to os.getcwd()
        assert result


# ---------------------------------------------------------------------------
# Unit tests for write_block_response
# ---------------------------------------------------------------------------


class TestWriteBlockResponse:
    """Tests for write_block_response function."""

    def test_outputs_json_and_exits_2(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.write_block_response("test reason")
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert data["reason"] == "test reason"


# ---------------------------------------------------------------------------
# Unit tests for get_current_branch
# ---------------------------------------------------------------------------


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    @patch("branch_protection_guard.subprocess.run")
    def test_returns_branch_name(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="feature/test\n", stderr=""
        )
        result = branch_protection_guard.get_current_branch("/some/path")
        assert result == "feature/test"

    @patch("branch_protection_guard.subprocess.run")
    def test_blocks_on_exit_code_128(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="fatal: not a git repository"
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.get_current_branch("/not/a/repo")
        assert exc_info.value.code == 2

    @patch("branch_protection_guard.subprocess.run")
    def test_blocks_on_nonzero_exit_code(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="git error"
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.get_current_branch("/some/path")
        assert exc_info.value.code == 2

    @patch("branch_protection_guard.subprocess.run")
    def test_blocks_when_git_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.get_current_branch("/some/path")
        assert exc_info.value.code == 2

    @patch("branch_protection_guard.subprocess.run")
    def test_blocks_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.get_current_branch("/some/path")
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    def test_exits_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 0

    def test_exits_0_on_empty_input(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: ""),
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 0

    def test_exits_0_on_whitespace_input(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: "   "),
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 0

    def test_exits_0_on_invalid_json(self, monkeypatch):
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: "not json"),
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 0

    @patch("branch_protection_guard.get_current_branch")
    def test_exits_0_on_feature_branch(self, mock_branch, monkeypatch):
        mock_branch.return_value = "feature/my-feature"
        hook_input = json.dumps({"cwd": "/test", "tool_name": "Bash"})
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 0

    @patch("branch_protection_guard.get_current_branch")
    def test_blocks_on_main_branch(self, mock_branch, monkeypatch, capsys):
        mock_branch.return_value = "main"
        hook_input = json.dumps({"cwd": "/test", "tool_name": "Bash"})
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert "main" in data["reason"]

    @patch("branch_protection_guard.get_current_branch")
    def test_blocks_on_master_branch(self, mock_branch, monkeypatch, capsys):
        mock_branch.return_value = "master"
        hook_input = json.dumps({"cwd": "/test", "tool_name": "Bash"})
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert "master" in data["reason"]

    @patch("branch_protection_guard.get_current_branch")
    def test_blocks_on_unexpected_exception(
        self, mock_branch, monkeypatch, capsys
    ):
        mock_branch.side_effect = RuntimeError("unexpected")
        hook_input = json.dumps({"cwd": "/test", "tool_name": "Bash"})
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert "unexpected" in data["reason"]

    @patch("branch_protection_guard.get_current_branch")
    def test_reraises_system_exit(self, mock_branch, monkeypatch):
        mock_branch.side_effect = SystemExit(2)
        hook_input = json.dumps({"cwd": "/test", "tool_name": "Bash"})
        monkeypatch.setattr(
            "sys.stdin",
            MagicMock(isatty=lambda: False, read=lambda: hook_input),
        )
        with pytest.raises(SystemExit) as exc_info:
            branch_protection_guard.main()
        assert exc_info.value.code == 2
