"""Tests for complete_session_log.py session completion script."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "session-end" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import complete_session_log


class TestFindCurrentSessionLog:
    """Tests for _find_current_session_log function."""

    def test_returns_none_when_no_dir(self, tmp_path):
        assert complete_session_log._find_current_session_log(str(tmp_path / "missing")) is None

    def test_returns_none_when_empty(self, tmp_path):
        assert complete_session_log._find_current_session_log(str(tmp_path)) is None

    def test_finds_most_recent(self, tmp_path):
        f1 = tmp_path / "2026-01-01-session-1.json"
        f2 = tmp_path / "2026-01-02-session-2.json"
        f1.write_text("{}")
        f2.write_text("{}")
        result = complete_session_log._find_current_session_log(str(tmp_path))
        assert result is not None


class TestGetEndingCommit:
    """Tests for _get_ending_commit function."""

    @patch("complete_session_log.subprocess.run")
    def test_returns_commit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n")
        assert complete_session_log._get_ending_commit() == "abc1234"

    @patch("complete_session_log.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert complete_session_log._get_ending_commit() is None


class TestHandoffModified:
    """Tests for _test_handoff_modified function."""

    @patch("complete_session_log.subprocess.run")
    def test_detects_modified(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="HANDOFF.md\n")
        assert complete_session_log._test_handoff_modified() is True

    @patch("complete_session_log.subprocess.run")
    def test_not_modified(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="other-file.md\n")
        assert complete_session_log._test_handoff_modified() is False


class TestSerenaMemoryUpdated:
    """Tests for _test_serena_memory_updated function."""

    @patch("complete_session_log.subprocess.run")
    def test_detects_memory_changes(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=".serena/memories/test.md\n"
        )
        assert complete_session_log._test_serena_memory_updated() is True

    @patch("complete_session_log.subprocess.run")
    def test_no_changes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="src/app.py\n")
        assert complete_session_log._test_serena_memory_updated() is False


class TestUncommittedChanges:
    """Tests for _test_uncommitted_changes function."""

    @patch("complete_session_log.subprocess.run")
    def test_clean_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert complete_session_log._test_uncommitted_changes() is False

    @patch("complete_session_log.subprocess.run")
    def test_dirty_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="M file.py\n")
        assert complete_session_log._test_uncommitted_changes() is True


class TestPathContainment:
    """Tests for _validate_path_containment (CWE-22)."""

    def test_valid_path(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        session_file = sessions_dir / "test.json"
        session_file.write_text("{}")
        result = complete_session_log._validate_path_containment(
            str(session_file), str(sessions_dir)
        )
        assert result is not None

    def test_rejects_traversal(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        evil_path = tmp_path / "evil.json"
        evil_path.write_text("{}")
        result = complete_session_log._validate_path_containment(
            str(evil_path), str(sessions_dir)
        )
        assert result is None


class TestRunMarkdownLint:
    """Tests for _run_markdown_lint function."""

    @patch("complete_session_log.subprocess.run")
    def test_no_markdown_files(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="src/app.py\n")
        success, output = complete_session_log._run_markdown_lint()
        assert success is True
        assert "No markdown" in output
