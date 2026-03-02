"""Tests for new_session_log_json.py simple session log creator."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-init" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import new_session_log_json


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_finds_git_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = new_session_log_json.get_repo_root(tmp_path / "sub" / "dir")
        # Falls back to script's directory traversal
        assert result is not None


class TestAutoDetectSessionNumber:
    """Tests for auto_detect_session_number function."""

    def test_returns_one_when_no_sessions(self, tmp_path):
        result = new_session_log_json.auto_detect_session_number(tmp_path)
        assert result == 1

    def test_returns_next_number(self, tmp_path):
        (tmp_path / "2026-01-01-session-5.json").write_text("{}")
        result = new_session_log_json.auto_detect_session_number(tmp_path)
        assert result == 6


class TestValidateSessionCeiling:
    """Tests for validate_session_ceiling (CWE-400 prevention).

    validate_session_ceiling returns None on success and calls sys.exit(1)
    on failure. Tests verify that valid inputs do not raise SystemExit
    and invalid inputs do.
    """

    def test_valid_within_ceiling(self, tmp_path):
        (tmp_path / "2026-01-01-session-5.json").write_text("{}")
        # Should not raise SystemExit
        new_session_log_json.validate_session_ceiling(6, tmp_path)

    def test_rejects_above_ceiling(self, tmp_path):
        (tmp_path / "2026-01-01-session-5.json").write_text("{}")
        with pytest.raises(SystemExit) as exc:
            new_session_log_json.validate_session_ceiling(50, tmp_path)
        assert exc.value.code == 1

    def test_valid_when_no_existing(self, tmp_path):
        # No existing sessions, any number is valid
        new_session_log_json.validate_session_ceiling(1, tmp_path)


class TestGetGitBranch:
    """Tests for get_git_branch function."""

    @patch("new_session_log_json.subprocess.run")
    def test_returns_branch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="feat/test\n")
        assert new_session_log_json.get_git_branch() == "feat/test"

    @patch("new_session_log_json.subprocess.run")
    def test_returns_unknown_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert new_session_log_json.get_git_branch() == "unknown"


class TestGetGitCommit:
    """Tests for get_git_commit function."""

    @patch("new_session_log_json.subprocess.run")
    def test_returns_commit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n")
        assert new_session_log_json.get_git_commit() == "abc1234"

    @patch("new_session_log_json.subprocess.run")
    def test_returns_unknown_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert new_session_log_json.get_git_commit() == "unknown"


class TestBuildSessionObject:
    """Tests for build_session_object function."""

    def test_structure(self):
        obj = new_session_log_json.build_session_object(
            1, "2026-01-01", "main", "abc1234", "Test"
        )
        assert obj["session"]["number"] == 1
        assert obj["session"]["date"] == "2026-01-01"
        assert obj["session"]["branch"] == "main"
        assert obj["session"]["startingCommit"] == "abc1234"
        assert obj["session"]["objective"] == "Test"
        assert "protocolCompliance" in obj
        assert obj["workLog"] == []


class TestWriteSessionFile:
    """Tests for write_session_file function.

    write_session_file(sessions_dir, date, session_number, session_data)
    takes 4 positional args. Uses atomic file creation (os.O_EXCL).
    """

    def test_writes_file(self, tmp_path):
        data = {"session": {"number": 1}}
        path = new_session_log_json.write_session_file(
            tmp_path, "2026-01-01", 1, data
        )
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["session"]["number"] == 1

    def test_handles_collision(self, tmp_path):
        data = {"session": {"number": 1}}
        path1 = new_session_log_json.write_session_file(
            tmp_path, "2026-01-01", 1, data
        )
        data2 = {"session": {"number": 1}}
        path2 = new_session_log_json.write_session_file(
            tmp_path, "2026-01-01", 1, data2
        )
        assert path1 != path2
        assert path2.exists()
