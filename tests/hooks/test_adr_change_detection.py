#!/usr/bin/env python3
"""Tests for the ADR change detection hook.

Covers: project root detection, path traversal protection, detection
script execution, change message building, git repo validation.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks")
sys.path.insert(0, HOOK_DIR)

import adr_change_detection  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests for get_project_root
# ---------------------------------------------------------------------------


class TestGetProjectRoot:
    """Tests for get_project_root function."""

    def test_uses_env_when_valid(self, monkeypatch, tmp_path):
        # Create a directory structure that looks valid
        script_dir = str(tmp_path / "project" / ".claude" / "hooks")
        os.makedirs(script_dir, exist_ok=True)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
        result = adr_change_detection.get_project_root(script_dir)
        assert result == str(tmp_path / "project")

    def test_rejects_path_traversal(self, monkeypatch, tmp_path):
        # script_dir is NOT under the project dir
        script_dir = str(tmp_path / "other" / "dir")
        os.makedirs(script_dir, exist_ok=True)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
        result = adr_change_detection.get_project_root(script_dir)
        assert result is None

    def test_derives_from_script_location(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        # .claude/hooks/ -> two levels up = project root
        result = adr_change_detection.get_project_root("/project/.claude/hooks")
        assert result == "/project"

    def test_returns_none_on_empty_env(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "")
        result = adr_change_detection.get_project_root("/some/dir")
        # Empty string is falsy, falls to derivation
        assert result == os.path.dirname(os.path.dirname("/some/dir"))


# ---------------------------------------------------------------------------
# Unit tests for run_detection_script
# ---------------------------------------------------------------------------


class TestRunDetectionScript:
    """Tests for run_detection_script function."""

    @patch("adr_change_detection.subprocess.run")
    def test_returns_parsed_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "HasChanges": True,
                "Created": ["ADR-001.md"],
                "Modified": [],
                "Deleted": [],
            }),
            stderr="",
        )
        result = adr_change_detection.run_detection_script(
            "/path/to/script.ps1", "/project"
        )
        assert result["HasChanges"] is True
        assert result["Created"] == ["ADR-001.md"]

    @patch("adr_change_detection.subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error"
        )
        result = adr_change_detection.run_detection_script(
            "/path/to/script.ps1", "/project"
        )
        assert result is None

    @patch("adr_change_detection.subprocess.run")
    def test_returns_none_on_invalid_json(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="not json", stderr=""
        )
        result = adr_change_detection.run_detection_script(
            "/path/to/script.ps1", "/project"
        )
        assert result is None

    @patch("adr_change_detection.subprocess.run")
    def test_returns_none_on_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("pwsh not found")
        result = adr_change_detection.run_detection_script(
            "/path/to/script.ps1", "/project"
        )
        assert result is None

    @patch("adr_change_detection.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="pwsh", timeout=30
        )
        result = adr_change_detection.run_detection_script(
            "/path/to/script.ps1", "/project"
        )
        assert result is None


# ---------------------------------------------------------------------------
# Unit tests for build_change_message
# ---------------------------------------------------------------------------


class TestBuildChangeMessage:
    """Tests for build_change_message function."""

    def test_includes_created_files(self):
        result = {"Created": ["ADR-001.md"], "Modified": [], "Deleted": []}
        message = adr_change_detection.build_change_message(result)
        assert "**Created**: ADR-001.md" in message

    def test_includes_modified_files(self):
        result = {"Created": [], "Modified": ["ADR-002.md"], "Deleted": []}
        message = adr_change_detection.build_change_message(result)
        assert "**Modified**: ADR-002.md" in message

    def test_includes_deleted_files(self):
        result = {"Created": [], "Modified": [], "Deleted": ["ADR-003.md"]}
        message = adr_change_detection.build_change_message(result)
        assert "**Deleted**: ADR-003.md" in message

    def test_includes_blocking_gate(self):
        result = {"Created": ["ADR-001.md"], "Modified": [], "Deleted": []}
        message = adr_change_detection.build_change_message(result)
        assert "BLOCKING GATE" in message

    def test_includes_review_instructions(self):
        result = {"Created": ["ADR-001.md"], "Modified": [], "Deleted": []}
        message = adr_change_detection.build_change_message(result)
        assert "/adr-review" in message
        assert "6-agent debate" in message

    def test_multiple_files_joined(self):
        result = {
            "Created": ["ADR-001.md", "ADR-002.md"],
            "Modified": [],
            "Deleted": [],
        }
        message = adr_change_detection.build_change_message(result)
        assert "ADR-001.md, ADR-002.md" in message

    def test_excludes_empty_categories(self):
        result = {"Created": ["ADR-001.md"], "Modified": [], "Deleted": []}
        message = adr_change_detection.build_change_message(result)
        assert "**Modified**" not in message
        assert "**Deleted**" not in message


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    @patch("adr_change_detection.os.path.exists")
    @patch("adr_change_detection.get_project_root")
    def test_exits_0_when_not_git_repo(
        self, mock_root, mock_exists, tmp_path
    ):
        mock_root.return_value = str(tmp_path)
        mock_exists.return_value = False  # .git does not exist
        with pytest.raises(SystemExit) as exc_info:
            adr_change_detection.main()
        assert exc_info.value.code == 0

    @patch("adr_change_detection.os.path.isfile")
    @patch("adr_change_detection.os.path.exists")
    @patch("adr_change_detection.get_project_root")
    def test_exits_0_when_detect_script_missing(
        self, mock_root, mock_exists, mock_isfile, tmp_path
    ):
        mock_root.return_value = str(tmp_path)
        mock_exists.return_value = True  # .git exists
        mock_isfile.return_value = False  # detect script missing
        with pytest.raises(SystemExit) as exc_info:
            adr_change_detection.main()
        assert exc_info.value.code == 0

    @patch("adr_change_detection.run_detection_script")
    @patch("adr_change_detection.os.path.isfile")
    @patch("adr_change_detection.os.path.exists")
    @patch("adr_change_detection.get_project_root")
    def test_outputs_message_on_changes(
        self, mock_root, mock_exists, mock_isfile, mock_detect, capsys
    ):
        mock_root.return_value = "/project"
        mock_exists.return_value = True  # .git exists
        mock_isfile.return_value = True  # detect script exists
        mock_detect.return_value = {
            "HasChanges": True,
            "Created": ["ADR-050.md"],
            "Modified": [],
            "Deleted": [],
        }
        with pytest.raises(SystemExit) as exc_info:
            adr_change_detection.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "ADR Changes Detected" in captured.out
        assert "ADR-050.md" in captured.out

    @patch("adr_change_detection.run_detection_script")
    @patch("adr_change_detection.os.path.isfile")
    @patch("adr_change_detection.os.path.exists")
    @patch("adr_change_detection.get_project_root")
    def test_no_output_when_no_changes(
        self, mock_root, mock_exists, mock_isfile, mock_detect, capsys
    ):
        mock_root.return_value = "/project"
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_detect.return_value = {
            "HasChanges": False,
            "Created": [],
            "Modified": [],
            "Deleted": [],
        }
        with pytest.raises(SystemExit) as exc_info:
            adr_change_detection.main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "ADR Changes Detected" not in captured.out

    @patch("adr_change_detection.run_detection_script")
    @patch("adr_change_detection.os.path.isfile")
    @patch("adr_change_detection.os.path.exists")
    @patch("adr_change_detection.get_project_root")
    def test_exits_0_on_detection_failure(
        self, mock_root, mock_exists, mock_isfile, mock_detect
    ):
        mock_root.return_value = "/project"
        mock_exists.return_value = True
        mock_isfile.return_value = True
        mock_detect.return_value = None
        with pytest.raises(SystemExit) as exc_info:
            adr_change_detection.main()
        assert exc_info.value.code == 0

    @patch("adr_change_detection.os.path.isfile")
    @patch("adr_change_detection.os.path.exists")
    @patch("adr_change_detection.get_project_root")
    def test_exits_0_on_exception(
        self, mock_root, mock_exists, mock_isfile
    ):
        mock_root.return_value = "/project"
        mock_exists.return_value = True
        mock_isfile.return_value = True
        with patch(
            "adr_change_detection.run_detection_script",
            side_effect=RuntimeError("unexpected"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                adr_change_detection.main()
            assert exc_info.value.code == 0

    def test_exits_0_when_project_root_none(self, monkeypatch):
        with patch(
            "adr_change_detection.get_project_root", return_value=None
        ):
            with pytest.raises(SystemExit) as exc_info:
                adr_change_detection.main()
            assert exc_info.value.code == 0


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_adr_change_detection_as_script(self):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "adr_change_detection.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self):
        """Cover the sys.exit(0) in __main__ guard via runpy in-process execution."""
        import runpy

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "adr_change_detection.py"
        )
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
