#!/usr/bin/env python3
"""Tests for the invoke_branch_context_guard PreToolUse hook.

Covers: branch mismatch detection, session log parsing, git operations,
exit codes (0=allow, 2=block on mismatch), fail-open on errors.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse")
sys.path.insert(0, HOOK_DIR)

import invoke_branch_context_guard  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for get_current_branch
# ---------------------------------------------------------------------------


class TestGetCurrentBranch:
    @patch("invoke_branch_context_guard.subprocess.run")
    def test_returns_branch_name(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="feat/my-feature\n"
        )
        result = invoke_branch_context_guard.get_current_branch("/project")
        assert result == "feat/my-feature"

    @patch("invoke_branch_context_guard.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = invoke_branch_context_guard.get_current_branch("/project")
        assert result is None

    @patch("invoke_branch_context_guard.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        result = invoke_branch_context_guard.get_current_branch("/project")
        assert result is None

    @patch("invoke_branch_context_guard.subprocess.run")
    def test_returns_none_when_git_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")
        result = invoke_branch_context_guard.get_current_branch("/project")
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests for get_session_branch
# ---------------------------------------------------------------------------


class TestGetSessionBranch:
    def test_extracts_branch_from_json(self, tmp_path):
        log = tmp_path / "session.json"
        log.write_text(json.dumps({"branch": "feat/test-branch"}))
        result = invoke_branch_context_guard.get_session_branch(log)
        assert result == "feat/test-branch"

    def test_returns_none_for_missing_branch(self, tmp_path):
        log = tmp_path / "session.json"
        log.write_text(json.dumps({"objective": "test"}))
        result = invoke_branch_context_guard.get_session_branch(log)
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path):
        log = tmp_path / "session.json"
        log.write_text("not json")
        result = invoke_branch_context_guard.get_session_branch(log)
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests for write_block_response
# ---------------------------------------------------------------------------


class TestWriteBlockResponse:
    def test_outputs_json_block(self, capsys):
        invoke_branch_context_guard.write_block_response("mismatch")
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert data["reason"] == "mismatch"


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        result = invoke_branch_context_guard.main()
        assert result == 0

    def test_exits_0_on_empty_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        result = invoke_branch_context_guard.main()
        assert result == 0

    def test_exits_0_on_invalid_json(self, mock_stdin: Callable[[str], None]):
        mock_stdin("not json")
        result = invoke_branch_context_guard.main()
        assert result == 0

    def test_exits_0_for_non_git_command(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps({"tool_input": {"command": "ls -la"}})
        )
        result = invoke_branch_context_guard.main()
        assert result == 0

    def test_exits_0_for_missing_command(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_input": {}}))
        result = invoke_branch_context_guard.main()
        assert result == 0

    @patch("invoke_branch_context_guard.get_today_session_log", return_value=None)
    @patch("invoke_branch_context_guard.get_current_branch", return_value="main")
    @patch("invoke_branch_context_guard.get_project_directory", return_value="/project")
    @patch("os.path.isdir", return_value=True)
    def test_exits_0_when_no_session_log(
        self, _isdir, _dir, _branch, _log, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git push origin main"}})
        )
        result = invoke_branch_context_guard.main()
        assert result == 0

    @patch("invoke_branch_context_guard.get_session_branch", return_value="feat/expected")
    @patch("invoke_branch_context_guard.get_today_session_log")
    @patch("invoke_branch_context_guard.get_current_branch", return_value="feat/expected")
    @patch("invoke_branch_context_guard.get_project_directory", return_value="/project")
    @patch("os.path.isdir", return_value=True)
    def test_exits_0_when_branches_match(
        self,
        _isdir,
        _dir,
        _branch,
        mock_log,
        _session_branch,
        mock_stdin: Callable[[str], None],
        tmp_path,
    ):
        log_file = tmp_path / "session.json"
        log_file.write_text("{}")
        mock_log.return_value = log_file
        mock_stdin(
            json.dumps({"tool_input": {"command": "git commit -m 'test'"}})
        )
        result = invoke_branch_context_guard.main()
        assert result == 0

    @patch("invoke_branch_context_guard.get_session_branch", return_value="feat/expected")
    @patch("invoke_branch_context_guard.get_today_session_log")
    @patch("invoke_branch_context_guard.get_current_branch", return_value="feat/wrong")
    @patch("invoke_branch_context_guard.get_project_directory", return_value="/project")
    @patch("os.path.isdir", return_value=True)
    def test_exits_2_on_branch_mismatch(
        self,
        _isdir,
        _dir,
        _branch,
        mock_log,
        _session_branch,
        mock_stdin: Callable[[str], None],
        tmp_path,
        capsys,
    ):
        log_file = tmp_path / "session.json"
        log_file.write_text("{}")
        mock_log.return_value = log_file
        mock_stdin(
            json.dumps({"tool_input": {"command": "git push origin feat/wrong"}})
        )
        result = invoke_branch_context_guard.main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "feat/expected" in captured.out

    def test_fails_open_on_exception(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_input": None}))
        result = invoke_branch_context_guard.main()
        assert result == 0
