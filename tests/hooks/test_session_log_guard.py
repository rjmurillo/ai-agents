"""Tests for PreToolUse session_log_guard hook.

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

from session_log_guard import (
    get_project_directory,
    get_today_session_log,
    is_git_commit_command,
    main,
    check_session_log_evidence,
)


class TestIsGitCommitCommand:
    """Tests for git commit command detection."""

    def test_git_commit(self) -> None:
        assert is_git_commit_command("git commit -m 'test'") is True

    def test_git_ci_alias(self) -> None:
        assert is_git_commit_command("git ci -m 'test'") is True

    def test_git_commit_with_prefix(self) -> None:
        assert is_git_commit_command("  git commit -am 'test'") is True

    def test_not_git_command(self) -> None:
        assert is_git_commit_command("git push origin main") is False

    def test_git_status(self) -> None:
        assert is_git_commit_command("git status") is False

    def test_empty_string(self) -> None:
        assert is_git_commit_command("") is False

    def test_none_like(self) -> None:
        assert is_git_commit_command("   ") is False

    def test_echo_git_commit(self) -> None:
        """Echo containing git commit in quotes should not match."""
        assert is_git_commit_command('echo "git commit"') is False

    def test_git_commit_amend(self) -> None:
        assert is_git_commit_command("git commit --amend") is True


class TestGetProjectDirectory:
    """Tests for project directory resolution."""

    def test_env_var_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/some/project")
        assert get_project_directory() == "/some/project"

    def test_git_walk_up(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert get_project_directory() == str(tmp_path)

    def test_fallback_to_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        # No .git in hierarchy (tmp_path is usually under /tmp)
        result = get_project_directory()
        # Should fall back to cwd
        assert os.path.isabs(result)


class TestGetTodaySessionLog:
    """Tests for session log discovery."""

    def test_no_directory(self, tmp_path: Path) -> None:
        assert get_today_session_log(str(tmp_path / "nonexistent"), "2026-03-01") is None

    def test_no_logs(self, tmp_path: Path) -> None:
        assert get_today_session_log(str(tmp_path), "2026-03-01") is None

    def test_finds_log(self, tmp_path: Path) -> None:
        log_file = tmp_path / "2026-03-01-session-01.json"
        log_file.write_text('{"test": true}')
        result = get_today_session_log(str(tmp_path), "2026-03-01")
        assert result == str(log_file)

    def test_returns_most_recent(self, tmp_path: Path) -> None:
        log1 = tmp_path / "2026-03-01-session-01.json"
        log1.write_text('{"session": 1}')
        log2 = tmp_path / "2026-03-01-session-02.json"
        log2.write_text('{"session": 2}')
        # Touch log2 to make it newer
        log2.touch()
        result = get_today_session_log(str(tmp_path), "2026-03-01")
        assert result is not None
        assert "session-02" in result

    def test_wrong_date(self, tmp_path: Path) -> None:
        log_file = tmp_path / "2026-02-28-session-01.json"
        log_file.write_text('{"test": true}')
        assert get_today_session_log(str(tmp_path), "2026-03-01") is None


class TestCheckSessionLogEvidence:
    """Tests for session log validation."""

    def test_short_content_invalid(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text("{}")
        result = check_session_log_evidence(str(log))
        assert result["valid"] is False
        assert "empty" in result["reason"]

    def test_valid_content(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        content = json.dumps({"session_id": "test", "work": "did stuff", "extra": "x" * 100})
        log.write_text(content)
        result = check_session_log_evidence(str(log))
        assert result["valid"] is True
        assert "content" in result

    def test_json_with_few_keys(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        content = json.dumps({"only_key": "x" * 200})
        log.write_text(content)
        result = check_session_log_evidence(str(log))
        assert result["valid"] is False
        assert "required sections" in result["reason"]

    def test_non_json_content_valid(self, tmp_path: Path) -> None:
        log = tmp_path / "session.md"
        log.write_text("# Session Log\n" + "work done " * 20)
        result = check_session_log_evidence(str(log))
        assert result["valid"] is True

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = check_session_log_evidence(str(tmp_path / "missing.json"))
        assert result["valid"] is False
        assert "deleted" in result["reason"]

    def test_permission_error(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text("content")
        log.chmod(0o000)
        try:
            result = check_session_log_evidence(str(log))
            assert result["valid"] is False
            assert "permissions" in result["reason"] or "Error" in result["reason"]
        finally:
            log.chmod(0o644)

    def test_preview_truncated_to_200(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        content = json.dumps({"key1": "a" * 300, "key2": "b" * 300})
        log.write_text(content)
        result = check_session_log_evidence(str(log))
        assert result["valid"] is True
        assert len(result["content"]) <= 200


class TestMainAllow:
    """Tests for main() allowing commits."""

    def test_stdin_is_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", sys.stdin)
        with patch("session_log_guard.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    def test_whitespace_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("   "))
        assert main() == 0

    def test_no_tool_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_name": "Bash"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_no_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"file_path": "/some/file"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_non_commit_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"command": "git status"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_commit_with_valid_session_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log_content = json.dumps({"session_id": "test", "work": "stuff", "extra": "x" * 100})
        log_file = sessions_dir / "2026-03-01-session-01.json"
        log_file.write_text(log_content)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "git commit -m 'test'"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("session_log_guard.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            assert main() == 0

    def test_invalid_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{invalid json"))
        assert main() == 0


class TestMainBlock:
    """Tests for main() blocking commits."""

    def test_commit_without_session_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "git commit -m 'test'"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("session_log_guard.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            result = main()

        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "No Session Log Found" in captured.out

    def test_commit_with_empty_session_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log_file = sessions_dir / "2026-03-01-session-01.json"
        log_file.write_text("{}")  # Too short (< 100 chars)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "git commit -m 'test'"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("session_log_guard.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            result = main()

        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "Empty or Invalid" in captured.out

    def test_commit_with_ci_alias_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "git ci -m 'test'"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("session_log_guard.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            assert main() == 2
