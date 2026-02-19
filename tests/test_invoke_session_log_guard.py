"""Tests for invoke_session_log_guard.py PreToolUse hook."""

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

from invoke_session_log_guard import (  # noqa: E402
    MIN_SESSION_LOG_LENGTH,
    check_session_log_evidence,
    main,
)


class TestTestSessionLogEvidence:
    def test_valid_when_sufficient_content(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        content = json.dumps({"a": "b", "c": "d"}).ljust(MIN_SESSION_LOG_LENGTH + 10, " ")
        log_file.write_text(content, encoding="utf-8")
        result = check_session_log_evidence(log_file)
        assert result["valid"] is True
        assert "content" in result

    def test_invalid_when_too_short(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        log_file.write_text("{}", encoding="utf-8")
        result = check_session_log_evidence(log_file)
        assert result["valid"] is False
        assert "empty" in str(result["reason"]).lower()

    def test_invalid_when_json_has_too_few_properties(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        # Long enough content but only 1 property
        content = json.dumps({"only_one_key": "x" * 200})
        log_file.write_text(content, encoding="utf-8")
        result = check_session_log_evidence(log_file)
        assert result["valid"] is False
        assert "required sections" in str(result["reason"]).lower()

    def test_valid_for_non_json_content(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.md"
        content = "# Session Log\n" + "Work done: lots of things\n" * 20
        log_file.write_text(content, encoding="utf-8")
        result = check_session_log_evidence(log_file)
        assert result["valid"] is True

    def test_invalid_when_file_not_found(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "nonexistent.json"
        result = check_session_log_evidence(missing_file)
        assert result["valid"] is False
        assert "deleted" in str(result["reason"]).lower()

    def test_preview_capped_at_200(self, tmp_path: Path) -> None:
        log_file = tmp_path / "session.json"
        data = {"a": "x" * 300, "b": "y"}
        log_file.write_text(json.dumps(data), encoding="utf-8")
        result = check_session_log_evidence(log_file)
        assert result["valid"] is True
        assert len(str(result["content"])) <= 200


class TestMainAllowPath:
    @patch("invoke_session_log_guard.sys.stdin")
    def test_allows_when_tty(self, mock_stdin: MagicMock) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_session_log_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_empty_stdin(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_session_log_guard.sys.stdin", new_callable=StringIO)
    def test_allows_non_commit_commands(self, mock_stdin: StringIO) -> None:
        data = json.dumps({"tool_input": {"command": "git status"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_session_log_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_no_tool_input(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("{}")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_session_log_guard.sys.stdin", new_callable=StringIO)
    def test_failopen_on_invalid_json(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("not json")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainBlockPath:
    @patch("invoke_session_log_guard.os.path.isdir", return_value=True)
    @patch("invoke_session_log_guard.get_today_session_log", return_value=None)
    @patch("invoke_session_log_guard.get_project_directory", return_value="/tmp/test")
    @patch("invoke_session_log_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_commit_without_session_log(
        self,
        mock_stdin: StringIO,
        _mock_project_dir: MagicMock,
        _mock_session_log: MagicMock,
        _mock_isdir: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
            captured = capsys.readouterr()
            assert "BLOCKED" in captured.out

    @patch("invoke_session_log_guard.os.path.isdir", return_value=True)
    @patch("invoke_session_log_guard.check_session_log_evidence")
    @patch("invoke_session_log_guard.get_today_session_log")
    @patch("invoke_session_log_guard.get_project_directory", return_value="/tmp/test")
    @patch("invoke_session_log_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_commit_with_empty_session_log(
        self,
        mock_stdin: StringIO,
        _mock_project_dir: MagicMock,
        mock_session_log: MagicMock,
        mock_evidence: MagicMock,
        _mock_isdir: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_log = MagicMock()
        mock_log.name = "2026-02-12-session-1.json"
        mock_session_log.return_value = mock_log
        mock_evidence.return_value = {"valid": False, "reason": "Session log exists but is empty"}

        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
            captured = capsys.readouterr()
            assert "BLOCKED" in captured.out

    @patch("invoke_session_log_guard.check_session_log_evidence")
    @patch("invoke_session_log_guard.get_today_session_log")
    @patch("invoke_session_log_guard.get_project_directory", return_value="/tmp/test")
    @patch("invoke_session_log_guard.sys.stdin", new_callable=StringIO)
    def test_allows_commit_with_valid_session_log(
        self,
        mock_stdin: StringIO,
        _mock_project_dir: MagicMock,
        mock_session_log: MagicMock,
        mock_evidence: MagicMock,
    ) -> None:
        mock_log = MagicMock()
        mock_log.name = "2026-02-12-session-1.json"
        mock_session_log.return_value = mock_log
        mock_evidence.return_value = {"valid": True, "content": "preview"}

        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainFailOpen:
    @patch("invoke_session_log_guard.is_git_commit_command", side_effect=Exception("boom"))
    @patch("invoke_session_log_guard.sys.stdin", new_callable=StringIO)
    def test_failopen_on_exception(
        self,
        mock_stdin: StringIO,
        _mock_commit: MagicMock,
    ) -> None:
        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0
