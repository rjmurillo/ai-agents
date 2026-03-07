"""Tests for invoke_branch_context_guard.py PreToolUse hook.

Verifies that the hook:
1. Blocks git commit/push when branch mismatches session context
2. Allows operations when branches match
3. Fails open when session context unavailable
"""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for hook imports
_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks" / "PreToolUse"))

from invoke_branch_context_guard import (  # noqa: E402
    get_current_branch,
    get_session_branch,
    main,
    write_block_response,
)


class TestWriteBlockResponse:
    def test_outputs_json_with_block_decision(self, capsys: pytest.CaptureFixture[str]) -> None:
        write_block_response("test reason")
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert data["reason"] == "test reason"


class TestGetCurrentBranch:
    @patch("invoke_branch_context_guard.subprocess.run")
    def test_returns_branch_name(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="feat/my-feature\n", stderr="")
        result = get_current_branch("/tmp")
        assert result == "feat/my-feature"

    @patch("invoke_branch_context_guard.subprocess.run")
    def test_returns_none_on_failure(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = get_current_branch("/tmp")
        assert result is None

    @patch("invoke_branch_context_guard.subprocess.run")
    def test_returns_none_on_exception(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("git not found")
        result = get_current_branch("/tmp")
        assert result is None


class TestGetSessionBranch:
    def test_returns_branch_from_session_log(self, tmp_path: Path) -> None:
        session_log = tmp_path / "2025-01-01-session-01.json"
        session_log.write_text(json.dumps({"branch": "feat/test-branch"}))
        result = get_session_branch(session_log)
        assert result == "feat/test-branch"

    def test_returns_none_when_no_branch_field(self, tmp_path: Path) -> None:
        session_log = tmp_path / "2025-01-01-session-01.json"
        session_log.write_text(json.dumps({"other": "value"}))
        result = get_session_branch(session_log)
        assert result is None

    def test_returns_none_for_invalid_json(self, tmp_path: Path) -> None:
        session_log = tmp_path / "2025-01-01-session-01.json"
        session_log.write_text("not valid json")
        result = get_session_branch(session_log)
        assert result is None

    def test_returns_none_for_nonexistent_file(self, tmp_path: Path) -> None:
        session_log = tmp_path / "does-not-exist.json"
        result = get_session_branch(session_log)
        assert result is None


class TestMainAllowPath:
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_stdin_empty(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_branch_context_guard.sys.stdin")
    def test_allows_when_stdin_is_tty(self, mock_stdin: MagicMock) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_allows_on_invalid_json(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("not json")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_not_git_commit_or_push(self, mock_stdin: StringIO) -> None:
        hook_input = {"tool_input": {"command": "git status"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_branch_context_guard.get_project_directory")
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_no_sessions_dir(
        self, mock_stdin: StringIO, mock_project_dir: MagicMock, tmp_path: Path
    ) -> None:
        mock_project_dir.return_value = str(tmp_path)
        hook_input = {"tool_input": {"command": "git commit -m 'test'"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_branch_context_guard.get_current_branch")
    @patch("invoke_branch_context_guard.get_project_directory")
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_cannot_determine_branch(
        self,
        mock_stdin: StringIO,
        mock_project_dir: MagicMock,
        mock_get_branch: MagicMock,
        tmp_path: Path,
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        mock_project_dir.return_value = str(tmp_path)
        mock_get_branch.return_value = None

        hook_input = {"tool_input": {"command": "git commit -m 'test'"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_branch_context_guard.get_today_session_log")
    @patch("invoke_branch_context_guard.get_current_branch")
    @patch("invoke_branch_context_guard.get_project_directory")
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_no_session_log(
        self,
        mock_stdin: StringIO,
        mock_project_dir: MagicMock,
        mock_get_branch: MagicMock,
        mock_get_log: MagicMock,
        tmp_path: Path,
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        mock_project_dir.return_value = str(tmp_path)
        mock_get_branch.return_value = "feat/current"
        mock_get_log.return_value = None

        hook_input = {"tool_input": {"command": "git commit -m 'test'"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_branch_context_guard.get_session_branch")
    @patch("invoke_branch_context_guard.get_today_session_log")
    @patch("invoke_branch_context_guard.get_current_branch")
    @patch("invoke_branch_context_guard.get_project_directory")
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_no_branch_in_session(
        self,
        mock_stdin: StringIO,
        mock_project_dir: MagicMock,
        mock_get_branch: MagicMock,
        mock_get_log: MagicMock,
        mock_session_branch: MagicMock,
        tmp_path: Path,
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        mock_project_dir.return_value = str(tmp_path)
        mock_get_branch.return_value = "feat/current"
        mock_get_log.return_value = Path("session.json")
        mock_session_branch.return_value = None

        hook_input = {"tool_input": {"command": "git commit -m 'test'"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_branch_context_guard.get_session_branch")
    @patch("invoke_branch_context_guard.get_today_session_log")
    @patch("invoke_branch_context_guard.get_current_branch")
    @patch("invoke_branch_context_guard.get_project_directory")
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_branches_match(
        self,
        mock_stdin: StringIO,
        mock_project_dir: MagicMock,
        mock_get_branch: MagicMock,
        mock_get_log: MagicMock,
        mock_session_branch: MagicMock,
        tmp_path: Path,
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        mock_project_dir.return_value = str(tmp_path)
        mock_get_branch.return_value = "feat/my-feature"
        mock_get_log.return_value = Path("session.json")
        mock_session_branch.return_value = "feat/my-feature"

        hook_input = {"tool_input": {"command": "git commit -m 'test'"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainBlockPath:
    @patch("invoke_branch_context_guard.get_session_branch")
    @patch("invoke_branch_context_guard.get_today_session_log")
    @patch("invoke_branch_context_guard.get_current_branch")
    @patch("invoke_branch_context_guard.get_project_directory")
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_when_branches_mismatch(
        self,
        mock_stdin: StringIO,
        mock_project_dir: MagicMock,
        mock_get_branch: MagicMock,
        mock_get_log: MagicMock,
        mock_session_branch: MagicMock,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        mock_project_dir.return_value = str(tmp_path)
        mock_get_branch.return_value = "feat/wrong-branch"
        session_path = sessions_dir / "2025-01-01-session-01.json"
        session_path.write_text("{}")
        mock_get_log.return_value = session_path
        mock_session_branch.return_value = "feat/expected-branch"

        hook_input = {"tool_input": {"command": "git commit -m 'test'"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            result = main()

        assert result == 2
        captured = capsys.readouterr()
        assert "Branch Mismatch Detected" in captured.out
        # Check the JSON block response is in stdout
        lines = captured.out.strip().split("\n")
        json_line = lines[-1]
        data = json.loads(json_line)
        assert data["decision"] == "block"
        assert "wrong-branch" in data["reason"]
        assert "expected-branch" in data["reason"]

    @patch("invoke_branch_context_guard.get_session_branch")
    @patch("invoke_branch_context_guard.get_today_session_log")
    @patch("invoke_branch_context_guard.get_current_branch")
    @patch("invoke_branch_context_guard.get_project_directory")
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_on_push_with_mismatch(
        self,
        mock_stdin: StringIO,
        mock_project_dir: MagicMock,
        mock_get_branch: MagicMock,
        mock_get_log: MagicMock,
        mock_session_branch: MagicMock,
        tmp_path: Path,
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        mock_project_dir.return_value = str(tmp_path)
        mock_get_branch.return_value = "feat/wrong"
        session_path = sessions_dir / "session.json"
        session_path.write_text("{}")
        mock_get_log.return_value = session_path
        mock_session_branch.return_value = "feat/expected"

        hook_input = {"tool_input": {"command": "git push origin feat/wrong"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            result = main()

        assert result == 2


class TestFailOpen:
    @patch("invoke_branch_context_guard.get_project_directory")
    @patch("invoke_branch_context_guard.sys.stdin", new_callable=StringIO)
    def test_fails_open_on_exception(
        self, mock_stdin: StringIO, mock_project_dir: MagicMock
    ) -> None:
        mock_project_dir.side_effect = RuntimeError("unexpected error")

        hook_input = {"tool_input": {"command": "git commit -m 'test'"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            result = main()

        assert result == 0  # Fail open
