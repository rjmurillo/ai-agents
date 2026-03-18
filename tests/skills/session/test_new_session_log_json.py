"""Tests for new_session_log_json.py simple session log creator."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-init" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import new_session_log_json


class TestGetBranch:
    """Tests for _get_branch function."""

    @patch("new_session_log_json.subprocess.run")
    def test_returns_branch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="feat/test\n")
        assert new_session_log_json._get_branch() == "feat/test"

    @patch("new_session_log_json.subprocess.run")
    def test_returns_unknown_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert new_session_log_json._get_branch() == "unknown"


class TestGetCommit:
    """Tests for _get_commit function."""

    @patch("new_session_log_json.subprocess.run")
    def test_returns_commit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n")
        assert new_session_log_json._get_commit() == "abc1234"

    @patch("new_session_log_json.subprocess.run")
    def test_returns_unknown_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert new_session_log_json._get_commit() == "unknown"


class TestGetRepoRoot:
    """Tests for _get_repo_root function."""

    @patch("new_session_log_json.subprocess.run")
    def test_returns_repo_root(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="/repo/.git\n")
        assert new_session_log_json._get_repo_root() == "/repo"

    @patch("new_session_log_json.subprocess.run")
    def test_returns_workspace_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = new_session_log_json._get_repo_root()
        assert result is not None


class TestMain:
    """Tests for main entry point."""

    @patch("new_session_log_json._get_repo_root")
    @patch("new_session_log_json._get_branch")
    @patch("new_session_log_json._get_commit")
    def test_creates_session_file(self, mock_commit, mock_branch, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        mock_branch.return_value = "feat/test"
        mock_commit.return_value = "abc1234"
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        exit_code = new_session_log_json.main([
            "--session-number", "1",
            "--objective", "test",
        ])
        assert exit_code == 0

        # Verify a session file was created
        files = list(sessions_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["session"]["number"] == 1
        assert data["session"]["branch"] == "feat/test"
        assert data["session"]["startingCommit"] == "abc1234"
        assert "protocolCompliance" in data
        assert data["workLog"] == []

    @patch("new_session_log_json._get_repo_root")
    @patch("new_session_log_json._get_branch")
    @patch("new_session_log_json._get_commit")
    def test_auto_detects_session_number(self, mock_commit, mock_branch, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        mock_branch.return_value = "main"
        mock_commit.return_value = "def5678"
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "2026-01-01-session-5.json").write_text("{}")

        exit_code = new_session_log_json.main(["--objective", "test"])
        assert exit_code == 0

        files = [f for f in sessions_dir.glob("*.json") if "session-6" in f.name]
        assert len(files) == 1

    @patch("new_session_log_json._get_repo_root")
    @patch("new_session_log_json._get_branch")
    @patch("new_session_log_json._get_commit")
    def test_rejects_session_above_ceiling(self, mock_commit, mock_branch, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        mock_branch.return_value = "main"
        mock_commit.return_value = "abc1234"
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "2026-01-01-session-5.json").write_text("{}")

        exit_code = new_session_log_json.main([
            "--session-number", "50",
            "--objective", "test",
        ])
        assert exit_code == 1

    @patch("new_session_log_json._get_repo_root")
    @patch("new_session_log_json._get_branch")
    @patch("new_session_log_json._get_commit")
    def test_handles_collision_retry(self, mock_commit, mock_branch, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        mock_branch.return_value = "feat/test"
        mock_commit.return_value = "abc1234"
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        # Create first session
        exit_code1 = new_session_log_json.main([
            "--session-number", "1",
            "--objective", "test1",
        ])
        assert exit_code1 == 0

        # Create second session with same number (should retry)
        exit_code2 = new_session_log_json.main([
            "--session-number", "1",
            "--objective", "test2",
        ])
        assert exit_code2 == 0

        files = list(sessions_dir.glob("*.json"))
        assert len(files) == 2

    @patch("new_session_log_json._get_repo_root")
    @patch("new_session_log_json._get_branch")
    @patch("new_session_log_json._get_commit")
    def test_not_on_main_detection(self, mock_commit, mock_branch, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        mock_branch.return_value = "feat/test"
        mock_commit.return_value = "abc1234"
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        new_session_log_json.main([
            "--session-number", "1",
            "--objective", "test",
        ])

        files = list(sessions_dir.glob("*.json"))
        data = json.loads(files[0].read_text())
        assert data["protocolCompliance"]["sessionStart"]["notOnMain"]["Complete"] is True
