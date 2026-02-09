"""Tests for hook_utilities package.

Migrated from tests/HookUtilities.Tests.ps1 per issue #1053.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.hook_utilities import (
    get_project_directory,
    get_today_session_log,
    get_today_session_logs,
    is_git_commit_command,
)


class TestGetProjectDirectory:
    def test_returns_claude_project_dir_when_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        assert get_project_directory() == str(tmp_path)

    def test_returns_cwd_when_no_git_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.warns(UserWarning, match="not found"):
            result = get_project_directory()
        assert result == str(tmp_path)

    def test_finds_git_by_walking_up(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        monkeypatch.chdir(sub_dir)
        result = get_project_directory()
        assert result == str(tmp_path)

    def test_ignores_empty_env_var(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "  ")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        result = get_project_directory()
        assert result == str(tmp_path)


class TestIsGitCommitCommand:
    def test_returns_true_for_git_commit(self) -> None:
        assert is_git_commit_command("git commit -m 'test'") is True

    def test_returns_true_for_git_ci(self) -> None:
        assert is_git_commit_command("git ci -m 'test'") is True

    def test_returns_false_for_git_status(self) -> None:
        assert is_git_commit_command("git status") is False

    def test_returns_false_for_empty_string(self) -> None:
        assert is_git_commit_command("") is False

    def test_returns_false_for_none(self) -> None:
        assert is_git_commit_command(None) is False

    def test_returns_true_when_preceded_by_whitespace(self) -> None:
        assert is_git_commit_command("  git commit -m 'test'") is True

    def test_returns_false_for_partial_match(self) -> None:
        assert is_git_commit_command("nogit commit") is False


class TestGetTodaySessionLog:
    def test_returns_none_for_nonexistent_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        with pytest.warns(UserWarning, match="not found"):
            result = get_today_session_log(str(nonexistent))
        assert result is None

    def test_does_not_throw_for_missing_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        with pytest.warns(UserWarning):
            result = get_today_session_log(str(nonexistent))
        assert result is None

    def test_returns_none_when_no_logs_exist(self, tmp_path: Path) -> None:
        result = get_today_session_log(str(tmp_path))
        assert result is None

    def test_returns_most_recent_log(self, tmp_path: Path) -> None:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        session1 = tmp_path / f"{today}-session-001.json"
        session2 = tmp_path / f"{today}-session-002.json"
        session1.write_text("{}")
        session2.write_text("{}")

        # Set predictable mtime ordering: session2 is newer
        os.utime(session1, (time.time() - 10, time.time() - 10))
        os.utime(session2, (time.time(), time.time()))

        result = get_today_session_log(str(tmp_path))
        assert result is not None
        assert result.name == f"{today}-session-002.json"

    def test_accepts_explicit_date(self, tmp_path: Path) -> None:
        session = tmp_path / "2025-01-15-session-001.json"
        session.write_text("{}")
        result = get_today_session_log(str(tmp_path), date="2025-01-15")
        assert result is not None
        assert result.name == "2025-01-15-session-001.json"

    def test_returns_none_for_wrong_date(self, tmp_path: Path) -> None:
        session = tmp_path / "2025-01-15-session-001.json"
        session.write_text("{}")
        result = get_today_session_log(str(tmp_path), date="2025-01-16")
        assert result is None


class TestGetTodaySessionLogs:
    def test_returns_empty_for_nonexistent_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        with pytest.warns(UserWarning, match="not found"):
            result = get_today_session_logs(str(nonexistent))
        assert result == []

    def test_does_not_throw_for_missing_dir(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent"
        with pytest.warns(UserWarning):
            result = get_today_session_logs(str(nonexistent))
        assert result == []

    def test_returns_all_today_logs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        yesterday = "2020-01-01"

        (tmp_path / f"{today}-session-001.json").write_text("{}")
        (tmp_path / f"{today}-session-002.json").write_text("{}")
        (tmp_path / f"{yesterday}-session-999.json").write_text("{}")

        result = get_today_session_logs(str(tmp_path))
        assert len(result) == 2
        for p in result:
            assert p.name.startswith(f"{today}-session-")


class TestModuleExports:
    def test_all_functions_importable(self) -> None:
        from scripts.hook_utilities import (
            get_project_directory,
            get_today_session_log,
            get_today_session_logs,
            is_git_commit_command,
        )
        assert callable(get_project_directory)
        assert callable(is_git_commit_command)
        assert callable(get_today_session_log)
        assert callable(get_today_session_logs)

    def test_all_exports_listed(self) -> None:
        import scripts.hook_utilities as mod
        expected = {
            "get_project_directory",
            "get_today_session_log",
            "get_today_session_logs",
            "is_git_commit_command",
        }
        assert set(mod.__all__) == expected
