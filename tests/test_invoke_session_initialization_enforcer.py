#!/usr/bin/env python3
"""Tests for SessionStart/invoke_session_initialization_enforcer.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add hook directory to path for import
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "SessionStart"),
)

import invoke_session_initialization_enforcer as hook


class TestGetCurrentBranch:
    """Tests for get_current_branch()."""

    def test_returns_branch_name(self) -> None:
        mock_result = MagicMock(returncode=0, stdout="feat/my-feature\n")
        target = "invoke_session_initialization_enforcer.subprocess.run"
        with patch(target, return_value=mock_result):
            assert hook.get_current_branch() == "feat/my-feature"

    def test_returns_none_on_failure(self) -> None:
        mock_result = MagicMock(returncode=128, stdout="")
        target = "invoke_session_initialization_enforcer.subprocess.run"
        with patch(target, return_value=mock_result):
            assert hook.get_current_branch() is None

    def test_returns_none_on_os_error(self) -> None:
        with patch(
            "invoke_session_initialization_enforcer.subprocess.run",
            side_effect=OSError("git not found"),
        ):
            assert hook.get_current_branch() is None


class TestIsProtectedBranch:
    """Tests for is_protected_branch()."""

    def test_main_is_protected(self) -> None:
        assert hook.is_protected_branch("main") is True

    def test_master_is_protected(self) -> None:
        assert hook.is_protected_branch("master") is True

    def test_feature_branch_not_protected(self) -> None:
        assert hook.is_protected_branch("feat/my-feature") is False

    def test_none_not_protected(self) -> None:
        assert hook.is_protected_branch(None) is False

    def test_empty_not_protected(self) -> None:
        assert hook.is_protected_branch("") is False


class TestMain:
    """Tests for main() entry point."""

    def test_protected_branch_outputs_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch.object(hook, "get_current_branch", return_value="main"),
            patch.object(hook, "get_project_directory", return_value="/tmp/test"),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "WARNING: On Protected Branch" in captured.out
        assert "main" in captured.out
        assert "git checkout -b" in captured.out

    def test_feature_branch_outputs_status(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch.object(hook, "get_current_branch", return_value="feat/test"),
            patch.object(hook, "get_project_directory", return_value="/tmp/test"),
            patch.object(hook, "get_session_status", return_value="2026-02-12-session-01.json"),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "feat/test" in captured.out
        assert "2026-02-12-session-01.json" in captured.out
        assert "ready" in captured.out

    def test_no_session_log_shows_init_hint(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch.object(hook, "get_current_branch", return_value="feat/test"),
            patch.object(hook, "get_project_directory", return_value="/tmp/test"),
            patch.object(hook, "get_session_status", return_value="none (run /session-init)"),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "/session-init" in captured.out

    def test_exception_fails_open(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(hook, "get_project_directory", side_effect=RuntimeError("boom")):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "boom" in captured.err
