"""Tests for new_session_log.py session log creator."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add script parent to path so session_init package can be found
SKILL_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-init"
SCRIPT_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SCRIPT_DIR))

import new_session_log


class TestAutoDetectSessionNumber:
    """Tests for _auto_detect_session_number function."""

    def test_returns_1_when_no_dir(self, tmp_path):
        result = new_session_log._auto_detect_session_number(str(tmp_path / "missing"))
        assert result == 1

    def test_returns_1_when_no_sessions(self, tmp_path):
        result = new_session_log._auto_detect_session_number(str(tmp_path))
        assert result == 1

    def test_returns_next_number(self, tmp_path):
        (tmp_path / "2026-01-01-session-5-test.json").write_text("{}")
        (tmp_path / "2026-01-02-session-3-test.json").write_text("{}")
        result = new_session_log._auto_detect_session_number(str(tmp_path))
        assert result == 6


class TestGetMaxExisting:
    """Tests for _get_max_existing_session function."""

    def test_returns_none_when_no_dir(self, tmp_path):
        assert new_session_log._get_max_existing_session(str(tmp_path / "missing")) is None

    def test_returns_none_when_empty(self, tmp_path):
        assert new_session_log._get_max_existing_session(str(tmp_path)) is None

    def test_returns_max(self, tmp_path):
        (tmp_path / "2026-01-01-session-10.json").write_text("{}")
        (tmp_path / "2026-01-02-session-7.json").write_text("{}")
        assert new_session_log._get_max_existing_session(str(tmp_path)) == 10


class TestDeriveObjective:
    """Tests for _derive_objective function."""

    def test_from_feature_branch(self):
        result = new_session_log._derive_objective("feat/session-protocol")
        assert result == "Work on session protocol"

    def test_from_fix_branch(self):
        result = new_session_log._derive_objective("fix/broken-tests")
        assert result == "Work on broken tests"

    def test_falls_back_to_commits(self):
        with patch("new_session_log.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="abc1234 feat: add new feature\n"
            )
            result = new_session_log._derive_objective("main")
            assert result is not None
            assert "feat: add new feature" in result

    def test_returns_empty_when_no_info(self):
        with patch("new_session_log.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = new_session_log._derive_objective("main")
            assert result == ""


class TestBuildSessionData:
    """Tests for _build_session_data function."""

    def test_structure(self):
        git_info = {
            "repo_root": "/repo",
            "branch": "main",
            "commit": "abc1234",
            "status": "clean",
        }
        data = new_session_log._build_session_data(
            git_info, 1, "Test objective", "2026-01-01"
        )
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
        git_info = {
            "repo_root": "/repo",
            "branch": "feat/test",
            "commit": "abc1234",
            "status": "clean",
        }
        data = new_session_log._build_session_data(
            git_info, 1, "Test", "2026-01-01"
        )
        assert data["protocolCompliance"]["sessionStart"]["notOnMain"]["Complete"] is True

        git_info["branch"] = "main"
        data = new_session_log._build_session_data(
            git_info, 1, "Test", "2026-01-01"
        )
        assert data["protocolCompliance"]["sessionStart"]["notOnMain"]["Complete"] is False


class TestWriteSessionFile:
    """Tests for _write_session_file function."""

    def test_writes_json(self, tmp_path):
        data = {"session": {"number": 1}, "test": True}
        path, num = new_session_log._write_session_file(
            str(tmp_path), data, "2026-01-01", "test objective"
        )
        assert os.path.exists(path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["test"] is True

    def test_atomic_creation(self, tmp_path):
        """Test O_EXCL prevents overwrite via collision retry."""
        data = {"session": {"number": 1}}
        path1, _ = new_session_log._write_session_file(
            str(tmp_path), data, "2026-01-01", "test"
        )
        assert os.path.exists(path1)

        data2 = {"session": {"number": 1}}
        path2, _ = new_session_log._write_session_file(
            str(tmp_path), data2, "2026-01-01", "test"
        )
        assert os.path.exists(path2)
        assert path2 != path1

    def test_creates_directory(self, tmp_path):
        sessions_dir = str(tmp_path / "deep" / "nested")
        data = {"session": {"number": 1}}
        path, _ = new_session_log._write_session_file(
            sessions_dir, data, "2026-01-01", "test"
        )
        assert os.path.exists(path)
        assert os.path.isdir(sessions_dir)


class TestRunValidation:
    """Tests for _run_validation function."""

    def test_returns_false_when_no_script(self, tmp_path):
        result = new_session_log._run_validation(
            str(tmp_path / "test.json"), str(tmp_path)
        )
        assert result is False

    @patch("new_session_log.subprocess.run")
    def test_returns_true_on_success(self, mock_run, tmp_path):
        # Create fake validation script
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "validate_session_json.py").write_text("# stub")
        mock_run.return_value = MagicMock(returncode=0)
        result = new_session_log._run_validation(
            str(tmp_path / "test.json"), str(tmp_path)
        )
        assert result is True

    @patch("new_session_log.subprocess.run")
    def test_returns_false_on_failure(self, mock_run, tmp_path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "validate_session_json.py").write_text("# stub")
        mock_run.return_value = MagicMock(returncode=1)
        result = new_session_log._run_validation(
            str(tmp_path / "test.json"), str(tmp_path)
        )
        assert result is False


class TestGetDescriptiveKeywords:
    """Tests for get_descriptive_keywords (via template_helpers)."""

    def test_extracts_keywords(self):
        from session_init.template_helpers import get_descriptive_keywords

        result = get_descriptive_keywords("Work on session protocol")
        assert "session" in result
        assert "protocol" in result

    def test_empty_objective(self):
        from session_init.template_helpers import get_descriptive_keywords

        assert get_descriptive_keywords("") == ""

    def test_limits_keywords(self):
        from session_init.template_helpers import get_descriptive_keywords

        result = get_descriptive_keywords(
            "session protocol validation testing checking verifying"
        )
        assert len(result.split("-")) <= 5


class TestMain:
    """Tests for main entry point."""

    @patch("new_session_log.get_git_info")
    def test_main_skip_validation(self, mock_git, tmp_path):
        mock_git.return_value = {
            "repo_root": str(tmp_path),
            "branch": "feat/test",
            "commit": "abc1234",
            "status": "clean",
        }
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        exit_code = new_session_log.main([
            "--session-number", "1",
            "--objective", "test objective",
            "--skip-validation",
        ])
        assert exit_code == 0
