"""Tests for new_session_log.py session log creator."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add script to path
SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-init" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import new_session_log


class TestGetGitInfo:
    """Tests for get_git_info function."""

    @patch("new_session_log.subprocess.run")
    def test_returns_repo_root(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="/repo\n")
        info = new_session_log.get_git_info()
        assert info["RepoRoot"] == "/repo"

    @patch("new_session_log.subprocess.run")
    def test_returns_branch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        info = new_session_log.get_git_info()
        assert info["Branch"] == "main"

    @patch("new_session_log.subprocess.run")
    def test_exits_when_not_in_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not a repo")
        with pytest.raises(SystemExit) as exc:
            new_session_log.get_git_info()
        assert exc.value.code == 1

    @patch("new_session_log.subprocess.run")
    def test_exits_on_timeout(self, mock_run):
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired(cmd="git", timeout=10)
        with pytest.raises(SystemExit) as exc:
            new_session_log.get_git_info()
        assert exc.value.code == 1


class TestGetDescriptiveKeywords:
    """Tests for get_descriptive_keywords function."""

    def test_extracts_keywords(self):
        result = new_session_log.get_descriptive_keywords("Work on session protocol")
        assert "session" in result
        assert "protocol" in result

    def test_removes_stop_words(self):
        result = new_session_log.get_descriptive_keywords("the work is done")
        assert "the" not in result
        assert "done" in result

    def test_empty_objective(self):
        assert new_session_log.get_descriptive_keywords("") == ""

    def test_limits_to_three_keywords(self):
        result = new_session_log.get_descriptive_keywords(
            "session protocol validation testing checking"
        )
        assert len(result.split("-")) <= 3


class TestAutoDetectSessionNumber:
    """Tests for auto_detect_session_number function."""

    def test_returns_none_when_no_dir(self, tmp_path):
        result = new_session_log.auto_detect_session_number(tmp_path / "missing")
        assert result is None

    def test_returns_none_when_no_sessions(self, tmp_path):
        result = new_session_log.auto_detect_session_number(tmp_path)
        assert result is None

    def test_returns_next_number(self, tmp_path):
        (tmp_path / "2026-01-01-session-5-test.json").write_text("{}")
        (tmp_path / "2026-01-02-session-3-test.json").write_text("{}")
        result = new_session_log.auto_detect_session_number(tmp_path)
        assert result == 6


class TestGetMaxExisting:
    """Tests for get_max_existing function."""

    def test_returns_none_when_empty(self, tmp_path):
        assert new_session_log.get_max_existing(tmp_path) is None

    def test_returns_max(self, tmp_path):
        (tmp_path / "2026-01-01-session-10.json").write_text("{}")
        (tmp_path / "2026-01-02-session-7.json").write_text("{}")
        assert new_session_log.get_max_existing(tmp_path) == 10


class TestDeriveObjective:
    """Tests for derive_objective function."""

    def test_from_feature_branch(self):
        result = new_session_log.derive_objective("feat/session-protocol")
        assert result == "Work on session protocol"

    def test_from_fix_branch(self):
        result = new_session_log.derive_objective("fix/broken-tests")
        assert result == "Work on broken tests"

    def test_falls_back_to_commits(self):
        with patch("new_session_log.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="abc1234 feat: add new feature\n"
            )
            result = new_session_log.derive_objective("main")
            assert result is not None
            assert "feat: add new feature" in result

    def test_returns_none_when_no_info(self):
        with patch("new_session_log.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = new_session_log.derive_objective("main")
            assert result is None


class TestBuildSessionData:
    """Tests for build_session_data function."""

    def test_structure(self):
        data = new_session_log.build_session_data(
            1, "2026-01-01", "main", "abc1234", "Test objective"
        )
        assert data["schemaVersion"] == "1.0"
        assert data["session"]["number"] == 1
        assert data["session"]["date"] == "2026-01-01"
        assert data["session"]["branch"] == "main"
        assert data["session"]["startingCommit"] == "abc1234"
        assert data["session"]["objective"] == "Test objective"
        assert "protocolCompliance" in data
        assert "sessionStart" in data["protocolCompliance"]
        assert "sessionEnd" in data["protocolCompliance"]
        assert data["workLog"] == []

    def test_not_on_main_detection(self):
        data = new_session_log.build_session_data(
            1, "2026-01-01", "feat/test", "abc1234", "Test"
        )
        assert data["protocolCompliance"]["sessionStart"]["notOnMain"]["Complete"] is True

        data = new_session_log.build_session_data(
            1, "2026-01-01", "main", "abc1234", "Test"
        )
        assert data["protocolCompliance"]["sessionStart"]["notOnMain"]["Complete"] is False


class TestWriteSessionFile:
    """Tests for write_session_file function."""

    def test_writes_json(self, tmp_path):
        data = {"session": {"number": 1}, "test": True}
        path = new_session_log.write_session_file(
            tmp_path, "2026-01-01", 1, "test objective", data
        )
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["test"] is True

    def test_atomic_creation(self, tmp_path):
        """Test O_EXCL prevents overwrite."""
        data = {"session": {"number": 1}}
        path1 = new_session_log.write_session_file(
            tmp_path, "2026-01-01", 1, "test", data
        )
        assert path1.exists()

        data2 = {"session": {"number": 1}}
        path2 = new_session_log.write_session_file(
            tmp_path, "2026-01-01", 1, "test", data2
        )
        assert path2.exists()
        assert path2 != path1

    def test_creates_directory(self, tmp_path):
        sessions_dir = tmp_path / "deep" / "nested"
        data = {"session": {"number": 1}}
        path = new_session_log.write_session_file(
            sessions_dir, "2026-01-01", 1, "test", data
        )
        assert path.exists()
        assert sessions_dir.is_dir()


class TestValidateSessionLog:
    """Tests for validate_session_log function."""

    def test_valid_json_passes_syntax(self, tmp_path):
        session_file = tmp_path / "test.json"
        session_file.write_text('{"schemaVersion": "1.0"}')

        schema_dir = tmp_path / ".agents" / "schemas"
        schema_dir.mkdir(parents=True)
        (schema_dir / "session-log.schema.json").write_text("{}")

        # No validation script, so it will fail at script check
        result = new_session_log.validate_session_log(session_file, str(tmp_path))
        assert result is False  # script not found

    def test_invalid_json_fails(self, tmp_path):
        session_file = tmp_path / "bad.json"
        session_file.write_text("not json{")

        schema_dir = tmp_path / ".agents" / "schemas"
        schema_dir.mkdir(parents=True)
        (schema_dir / "session-log.schema.json").write_text("{}")

        result = new_session_log.validate_session_log(session_file, str(tmp_path))
        assert result is False
