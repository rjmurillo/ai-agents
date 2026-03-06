"""Tests for PreToolUse invoke_session_log_guard hook.

Verifies that git commit commands are blocked without a valid session log,
and allowed when a proper session log exists.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook directory to path for import
HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

from invoke_session_log_guard import (  # noqa: E402
    check_session_log_evidence,
    main,
)


class TestCheckSessionLogEvidence:
    """Tests for session log validation."""

    def test_short_content_invalid(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text("{}")
        result = check_session_log_evidence(log)
        assert result["valid"] is False
        assert "empty" in result["reason"]

    def test_valid_content(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        content = json.dumps({"session_id": "test", "work": "did stuff", "extra": "x" * 100})
        log.write_text(content)
        result = check_session_log_evidence(log)
        assert result["valid"] is True
        assert "content" in result

    def test_json_with_few_keys(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        content = json.dumps({"only_key": "x" * 200})
        log.write_text(content)
        result = check_session_log_evidence(log)
        assert result["valid"] is False
        assert "required sections" in result["reason"]

    def test_non_json_content_valid(self, tmp_path: Path) -> None:
        log = tmp_path / "session.md"
        log.write_text("# Session Log\n" + "work done " * 20)
        result = check_session_log_evidence(log)
        assert result["valid"] is True

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = check_session_log_evidence(tmp_path / "missing.json")
        assert result["valid"] is False
        assert "deleted" in result["reason"]

    def test_permission_error(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text("content")
        log.chmod(0o000)
        try:
            result = check_session_log_evidence(log)
            assert result["valid"] is False
            assert "permissions" in result["reason"] or "Error" in result["reason"]
        finally:
            log.chmod(0o644)

    def test_preview_truncated_to_200(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        content = json.dumps({"key1": "a" * 300, "key2": "b" * 300})
        log.write_text(content)
        result = check_session_log_evidence(log)
        assert result["valid"] is True
        assert len(result["content"]) <= 200


class TestMainAllow:
    """Tests for main() allowing commits."""

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_stdin_is_tty(self, mock_skip, monkeypatch: pytest.MonkeyPatch) -> None:
        with patch("invoke_session_log_guard.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_empty_stdin(self, mock_skip, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_whitespace_stdin(self, mock_skip, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("   "))
        assert main() == 0

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_no_tool_input(self, mock_skip, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_name": "Bash"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_no_command(self, mock_skip, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"file_path": "/some/file"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_non_commit_command(self, mock_skip, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"command": "git status"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_commit_with_valid_session_log(
        self, mock_skip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log_content = json.dumps({"session_id": "test", "work": "stuff", "extra": "x" * 100})
        log_file = sessions_dir / "2026-03-01-session-01.json"
        log_file.write_text(log_content)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "git commit -m 'test'"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("invoke_session_log_guard.get_today_session_log", return_value=log_file):
            assert main() == 0

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_invalid_json_fails_open(self, mock_skip, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{invalid json"))
        assert main() == 0


class TestMainBlock:
    """Tests for main() blocking commits."""

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_commit_without_session_log(
        self, mock_skip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "git commit -m 'test'"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("invoke_session_log_guard.get_today_session_log", return_value=None):
            result = main()

        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "No Session Log Found" in captured.out

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_commit_with_empty_session_log(
        self, mock_skip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log_file = sessions_dir / "2026-03-01-session-01.json"
        log_file.write_text("{}")  # Too short (< 100 chars)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "git commit -m 'test'"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("invoke_session_log_guard.get_today_session_log", return_value=log_file):
            result = main()

        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "Empty or Invalid" in captured.out

    @patch("invoke_session_log_guard.skip_if_consumer_repo", return_value=False)
    def test_commit_with_ci_alias_blocked(
        self, mock_skip, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "git ci -m 'test'"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("invoke_session_log_guard.get_today_session_log", return_value=None):
            assert main() == 2
