#!/usr/bin/env python3
"""Tests for the invoke_adr_change_detection hook.

Covers: project root detection, path traversal protection, main entry point,
change detection via subprocess, git repo validation.
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

import invoke_adr_change_detection  # noqa: E402


# ---------------------------------------------------------------------------
# Unit tests for get_project_root
# ---------------------------------------------------------------------------


class TestGetProjectRoot:
    """Tests for get_project_root function."""

    def test_uses_env_when_valid(self, monkeypatch, tmp_path):
        # Create a directory structure that looks valid
        hook_dir = tmp_path / "project" / ".claude" / "hooks"
        hook_dir.mkdir(parents=True)
        fake_script = hook_dir / "invoke_adr_change_detection.py"
        fake_script.write_text("# stub")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
        # The function uses __file__ internally, so we patch it
        with patch.object(
            invoke_adr_change_detection,
            "__file__",
            str(fake_script),
        ):
            result = invoke_adr_change_detection.get_project_root()
        assert result == str(tmp_path / "project")

    def test_rejects_path_traversal(self, monkeypatch, tmp_path):
        # Script is NOT under the project dir
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
        result = invoke_adr_change_detection.get_project_root()
        assert result is None

    def test_derives_from_script_location(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        # Falls back to parents[2] of __file__
        result = invoke_adr_change_detection.get_project_root()
        assert result is not None

    def test_falls_back_to_derivation_on_empty_env(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "")
        result = invoke_adr_change_detection.get_project_root()
        # Empty string is falsy, falls to script-based derivation
        assert result is not None


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main entry point."""

    @pytest.fixture(autouse=True)
    def _no_consumer_repo_skip(self):
        with patch("invoke_adr_change_detection.skip_if_consumer_repo", return_value=False):
            yield

    @patch("invoke_adr_change_detection.skip_if_consumer_repo", return_value=True)
    def test_exits_0_when_consumer_repo(self, mock_skip):
        result = invoke_adr_change_detection.main()
        assert result == 0

    @patch("invoke_adr_change_detection.get_project_root", return_value=None)
    def test_exits_0_when_project_root_none(self, mock_root):
        result = invoke_adr_change_detection.main()
        assert result == 0

    @patch("invoke_adr_change_detection.get_project_root")
    def test_exits_0_when_not_git_repo(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        result = invoke_adr_change_detection.main()
        assert result == 0

    @patch("invoke_adr_change_detection.get_project_root")
    def test_exits_0_when_detect_script_missing(self, mock_root, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_root.return_value = str(tmp_path)
        result = invoke_adr_change_detection.main()
        assert result == 0

    @pytest.fixture
    def project_with_detect_script(self, tmp_path):
        """Create a tmp project with .git dir and stub detect script."""
        (tmp_path / ".git").mkdir()
        detect_script = (
            tmp_path / ".claude" / "skills" / "adr-review" / "scripts" / "detect_adr_changes.py"
        )
        detect_script.parent.mkdir(parents=True)
        detect_script.write_text("# stub")
        return tmp_path

    @patch("invoke_adr_change_detection.subprocess.run")
    @patch("invoke_adr_change_detection.get_project_root")
    def test_outputs_message_on_changes(
        self, mock_root, mock_run, project_with_detect_script, capsys
    ):
        mock_root.return_value = str(project_with_detect_script)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "HasChanges": True,
                "Created": ["ADR-050.md"],
                "Modified": [],
                "Deleted": [],
            }),
            stderr="",
        )
        result = invoke_adr_change_detection.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR Changes Detected" in captured.out
        assert "ADR-050.md" in captured.out

    @patch("invoke_adr_change_detection.subprocess.run")
    @patch("invoke_adr_change_detection.get_project_root")
    def test_no_output_when_no_changes(
        self, mock_root, mock_run, project_with_detect_script, capsys
    ):
        mock_root.return_value = str(project_with_detect_script)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "HasChanges": False,
                "Created": [],
                "Modified": [],
                "Deleted": [],
            }),
            stderr="",
        )
        result = invoke_adr_change_detection.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR Changes Detected" not in captured.out

    @patch("invoke_adr_change_detection.subprocess.run")
    @patch("invoke_adr_change_detection.get_project_root")
    def test_exits_0_on_detection_failure(
        self, mock_root, mock_run, project_with_detect_script
    ):
        mock_root.return_value = str(project_with_detect_script)
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = invoke_adr_change_detection.main()
        assert result == 0

    @patch("invoke_adr_change_detection.subprocess.run")
    @patch("invoke_adr_change_detection.get_project_root")
    def test_exits_0_on_invalid_json(
        self, mock_root, mock_run, project_with_detect_script
    ):
        mock_root.return_value = str(project_with_detect_script)
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        result = invoke_adr_change_detection.main()
        assert result == 0


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_adr_change_detection_as_script(self):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "invoke_adr_change_detection.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self):
        """Cover the sys.exit(main()) in __main__ guard via runpy in-process execution."""
        import runpy

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "invoke_adr_change_detection.py"
        )
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
