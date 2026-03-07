#!/usr/bin/env python3
"""Tests for hooks/invoke_adr_change_detection.py."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add hook directory to path for import
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / ".claude" / "hooks"),
)

import invoke_adr_change_detection as hook


class TestGetProjectRoot:
    """Tests for get_project_root()."""

    def test_uses_env_var_when_script_inside_root(self) -> None:
        """When CLAUDE_PROJECT_DIR contains the script, returns env var value."""
        # The real script lives inside the project root, so setting
        # CLAUDE_PROJECT_DIR to a parent of the script should succeed.
        project_root = str(Path(__file__).resolve().parents[1])
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": project_root}):
            result = hook.get_project_root()
            assert result == project_root

    def test_returns_none_on_traversal_attempt(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When CLAUDE_PROJECT_DIR is unrelated, returns None (fail-open)."""
        with patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": "/some/other/path"}):
            result = hook.get_project_root()
            # Script is NOT inside /some/other/path, so should return None
            assert result is None

    def test_derives_from_script_location_without_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            # Remove CLAUDE_PROJECT_DIR if set
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            result = hook.get_project_root()
            assert result is not None


class TestMain:
    """Tests for main() entry point."""

    def test_exits_zero_when_no_git_repo(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        with patch.object(hook, "get_project_root", return_value=str(tmp_path)):
            result = hook.main()
        assert result == 0

    def test_exits_zero_when_no_detect_script(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        with patch.object(hook, "get_project_root", return_value=str(tmp_path)):
            result = hook.main()
        assert result == 0

    def test_exits_zero_when_project_root_none(self) -> None:
        with patch.object(hook, "get_project_root", return_value=None):
            result = hook.main()
        assert result == 0

    def test_outputs_adr_changes_when_detected(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        (tmp_path / ".git").mkdir()
        scripts_dir = tmp_path / ".claude" / "skills" / "adr-review" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "detect_adr_changes.py").write_text("", encoding="utf-8")

        detection_output = json.dumps(
            {
                "HasChanges": True,
                "Created": ["ADR-099-test.md"],
                "Modified": [],
                "Deleted": [],
            }
        )

        mock_result = MagicMock(returncode=0, stdout=detection_output, stderr="")
        with (
            patch.object(hook, "get_project_root", return_value=str(tmp_path)),
            patch("invoke_adr_change_detection.subprocess.run", return_value=mock_result),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "ADR Changes Detected" in captured.out
        assert "ADR-099-test.md" in captured.out
        assert "/adr-review" in captured.out

    def test_no_output_when_no_changes(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        (tmp_path / ".git").mkdir()
        scripts_dir = tmp_path / ".claude" / "skills" / "adr-review" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "detect_adr_changes.py").write_text("", encoding="utf-8")

        detection_output = json.dumps(
            {
                "HasChanges": False,
                "Created": [],
                "Modified": [],
                "Deleted": [],
            }
        )
        mock_result = MagicMock(returncode=0, stdout=detection_output, stderr="")
        with (
            patch.object(hook, "get_project_root", return_value=str(tmp_path)),
            patch("invoke_adr_change_detection.subprocess.run", return_value=mock_result),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_handles_script_failure_gracefully(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        (tmp_path / ".git").mkdir()
        scripts_dir = tmp_path / ".claude" / "skills" / "adr-review" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "detect_adr_changes.py").write_text("", encoding="utf-8")

        mock_result = MagicMock(returncode=1, stdout="", stderr="git error")
        with (
            patch.object(hook, "get_project_root", return_value=str(tmp_path)),
            patch("invoke_adr_change_detection.subprocess.run", return_value=mock_result),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "exited with code 1" in captured.err

    def test_modified_and_deleted_shown(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        (tmp_path / ".git").mkdir()
        scripts_dir = tmp_path / ".claude" / "skills" / "adr-review" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "detect_adr_changes.py").write_text("", encoding="utf-8")

        detection_output = json.dumps(
            {
                "HasChanges": True,
                "Created": [],
                "Modified": ["ADR-001.md"],
                "Deleted": ["ADR-002.md"],
            }
        )
        mock_result = MagicMock(returncode=0, stdout=detection_output, stderr="")
        with (
            patch.object(hook, "get_project_root", return_value=str(tmp_path)),
            patch("invoke_adr_change_detection.subprocess.run", return_value=mock_result),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "**Modified**: ADR-001.md" in captured.out
        assert "**Deleted**: ADR-002.md" in captured.out
