#!/usr/bin/env python3
"""Tests for the invoke_branch_protection_guard hook.

Covers all branches: allow on feature branch, block on main/master,
git failures, missing input, invalid JSON, tty input, env fallback.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Callable

# Add hook directory to path for direct imports
HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse")
sys.path.insert(0, HOOK_DIR)

import invoke_branch_protection_guard  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for get_working_directory
# ---------------------------------------------------------------------------


class TestGetWorkingDirectory:
    """Tests for get_working_directory function."""

    def test_uses_cwd_from_hook_input(self):
        result = invoke_branch_protection_guard.get_working_directory(
            {"cwd": "/some/path"}
        )
        assert result == "/some/path"

    def test_strips_whitespace_from_cwd(self):
        result = invoke_branch_protection_guard.get_working_directory(
            {"cwd": "  /some/path  "}
        )
        assert result == "/some/path"

    def test_falls_back_to_env_var(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/env/path")
        result = invoke_branch_protection_guard.get_working_directory({"cwd": ""})
        assert result == "/env/path"

    def test_falls_back_to_env_var_when_cwd_missing(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/env/path")
        result = invoke_branch_protection_guard.get_working_directory({})
        assert result == "/env/path"

    def test_falls_back_to_os_getcwd(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = invoke_branch_protection_guard.get_working_directory({"cwd": ""})
        assert result  # Should return current working directory

    def test_ignores_whitespace_only_cwd(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/env/path")
        result = invoke_branch_protection_guard.get_working_directory(
            {"cwd": "   "}
        )
        assert result == "/env/path"

    def test_ignores_whitespace_only_env(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "   ")
        result = invoke_branch_protection_guard.get_working_directory({"cwd": ""})
        # Falls through to os.getcwd()
        assert result


# ---------------------------------------------------------------------------
# Unit tests for write_block_response
# ---------------------------------------------------------------------------


class TestWriteBlockResponse:
    """Tests for write_block_response function."""

    def test_outputs_json_block_response(self, capsys):
        invoke_branch_protection_guard.write_block_response("test reason")
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert data["reason"] == "test reason"


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    def test_exits_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        result = invoke_branch_protection_guard.main()
        assert result == 0

    def test_exits_0_on_empty_input(self, mock_stdin: "Callable[[str], None]"):
        mock_stdin("")
        result = invoke_branch_protection_guard.main()
        assert result == 0

    def test_exits_0_on_whitespace_input(self, mock_stdin: "Callable[[str], None]"):
        mock_stdin("   ")
        result = invoke_branch_protection_guard.main()
        assert result == 0

    def test_exits_0_on_invalid_json(self, mock_stdin: "Callable[[str], None]"):
        mock_stdin("not json")
        result = invoke_branch_protection_guard.main()
        assert result == 0

    @patch("invoke_branch_protection_guard.subprocess.run")
    def test_exits_0_on_feature_branch(
        self, mock_run, mock_stdin: "Callable[[str], None]"
    ):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="feature/my-feature\n", stderr=""
        )
        mock_stdin(json.dumps({"cwd": "/test", "tool_name": "Bash"}))
        result = invoke_branch_protection_guard.main()
        assert result == 0

    @patch("invoke_branch_protection_guard.subprocess.run")
    def test_blocks_on_main_branch(
        self, mock_run, mock_stdin: "Callable[[str], None]", capsys
    ):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="main\n", stderr=""
        )
        mock_stdin(json.dumps({"cwd": "/test", "tool_name": "Bash"}))
        result = invoke_branch_protection_guard.main()
        assert result == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert "main" in data["reason"]

    @patch("invoke_branch_protection_guard.subprocess.run")
    def test_blocks_on_master_branch(
        self, mock_run, mock_stdin: "Callable[[str], None]", capsys
    ):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="master\n", stderr=""
        )
        mock_stdin(json.dumps({"cwd": "/test", "tool_name": "Bash"}))
        result = invoke_branch_protection_guard.main()
        assert result == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert "master" in data["reason"]

    @patch("invoke_branch_protection_guard.subprocess.run")
    def test_blocks_on_unexpected_exception(
        self, mock_run, mock_stdin: "Callable[[str], None]", capsys
    ):
        mock_run.side_effect = RuntimeError("unexpected")
        mock_stdin(json.dumps({"cwd": "/test", "tool_name": "Bash"}))
        result = invoke_branch_protection_guard.main()
        assert result == 2
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert "unexpected" in data["reason"]

    @patch("invoke_branch_protection_guard.subprocess.run")
    def test_blocks_on_exit_code_128(
        self, mock_run, mock_stdin: "Callable[[str], None]", capsys
    ):
        mock_run.return_value = MagicMock(
            returncode=128, stdout="", stderr="fatal: not a git repository"
        )
        mock_stdin(json.dumps({"cwd": "/not/a/repo", "tool_name": "Bash"}))
        result = invoke_branch_protection_guard.main()
        assert result == 2

    @patch("invoke_branch_protection_guard.subprocess.run")
    def test_blocks_on_nonzero_exit_code(
        self, mock_run, mock_stdin: "Callable[[str], None]"
    ):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="git error"
        )
        mock_stdin(json.dumps({"cwd": "/some/path", "tool_name": "Bash"}))
        result = invoke_branch_protection_guard.main()
        assert result == 2

    @patch("invoke_branch_protection_guard.subprocess.run")
    def test_blocks_when_git_not_found(
        self, mock_run, mock_stdin: "Callable[[str], None]"
    ):
        mock_run.side_effect = FileNotFoundError("git not found")
        mock_stdin(json.dumps({"cwd": "/some/path", "tool_name": "Bash"}))
        result = invoke_branch_protection_guard.main()
        assert result == 2

    @patch("invoke_branch_protection_guard.subprocess.run")
    def test_blocks_on_timeout(self, mock_run, mock_stdin: "Callable[[str], None]"):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        mock_stdin(json.dumps({"cwd": "/some/path", "tool_name": "Bash"}))
        result = invoke_branch_protection_guard.main()
        assert result == 2
