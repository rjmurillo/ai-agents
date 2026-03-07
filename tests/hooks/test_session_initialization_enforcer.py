"""Tests for SessionStart invoke_session_initialization_enforcer hook.

Verifies that protected branch warnings are displayed, git state is injected,
and session log status is reported at session start.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart"
sys.path.insert(0, str(HOOK_DIR))

from invoke_session_initialization_enforcer import (  # noqa: E402
    PROTECTED_BRANCHES,
    get_current_branch,
    is_protected_branch,
    main,
)


class TestIsProtectedBranch:
    """Tests for protected branch detection."""

    def test_main(self) -> None:
        assert is_protected_branch("main") is True

    def test_master(self) -> None:
        assert is_protected_branch("master") is True

    def test_feature_branch(self) -> None:
        assert is_protected_branch("feat/my-feature") is False

    def test_none(self) -> None:
        assert is_protected_branch(None) is False

    def test_empty(self) -> None:
        assert is_protected_branch("") is False


class TestGetCurrentBranch:
    """Tests for git branch detection."""

    def test_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "feat/my-feature\n"
        with patch("invoke_session_initialization_enforcer.subprocess.run", return_value=mock_result):
            assert get_current_branch() == "feat/my-feature"

    def test_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        with patch("invoke_session_initialization_enforcer.subprocess.run", return_value=mock_result):
            assert get_current_branch() is None

    def test_git_not_found(self) -> None:
        with patch(
            "invoke_session_initialization_enforcer.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert get_current_branch() is None

    def test_oserror(self) -> None:
        with patch(
            "invoke_session_initialization_enforcer.subprocess.run",
            side_effect=OSError("error"),
        ):
            assert get_current_branch() is None


class TestProtectedBranches:
    """Tests for the constant."""

    def test_contains_main_and_master(self) -> None:
        assert "main" in PROTECTED_BRANCHES
        assert "master" in PROTECTED_BRANCHES


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    target = "invoke_session_initialization_enforcer.skip_if_consumer_repo"
    with patch(target, return_value=False):
        yield


class TestMainProtectedBranch:
    """Tests for main() on protected branch."""

    def test_main_branch_warning(self, capsys: pytest.CaptureFixture) -> None:
        mod = "invoke_session_initialization_enforcer"
        with patch(f"{mod}.get_project_directory", return_value="/project"):
            with patch(f"{mod}.get_current_branch", return_value="main"):
                assert main() == 0

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Protected Branch" in captured.out


class TestMainFeatureBranch:
    """Tests for main() on feature branch."""

    def test_feature_branch_status(self, capsys: pytest.CaptureFixture) -> None:
        mod = "invoke_session_initialization_enforcer"
        with patch(f"{mod}.get_project_directory", return_value="/project"):
            with patch(f"{mod}.get_current_branch", return_value="feat/test"):
                with patch(f"{mod}.get_today_session_log", return_value=None):
                    assert main() == 0

        captured = capsys.readouterr()
        assert "feat/test" in captured.out

    def test_with_session_log(self, capsys: pytest.CaptureFixture, tmp_path) -> None:
        mod = "invoke_session_initialization_enforcer"
        session_log = MagicMock()
        session_log.name = "2026-03-01-session-01.json"
        with patch(f"{mod}.get_project_directory", return_value="/project"):
            with patch(f"{mod}.get_current_branch", return_value="dev"):
                with patch(f"{mod}.get_today_session_log", return_value=session_log):
                    assert main() == 0

        captured = capsys.readouterr()
        assert "2026-03-01-session-01.json" in captured.out


class TestMainErrorHandling:
    """Tests for main() error handling."""

    def test_exception_fails_open(self) -> None:
        with patch(
            "invoke_session_initialization_enforcer.get_project_directory",
            side_effect=RuntimeError("boom"),
        ):
            assert main() == 0

    def test_none_branch(self, capsys: pytest.CaptureFixture) -> None:
        mod = "invoke_session_initialization_enforcer"
        with patch(f"{mod}.get_project_directory", return_value="/p"):
            with patch(f"{mod}.get_current_branch", return_value=None):
                with patch(f"{mod}.get_today_session_log", return_value=None):
                    assert main() == 0

        captured = capsys.readouterr()
        # Non-protected branch path, None branch displayed
        assert captured.out  # Some output produced


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_session_initialization_enforcer_as_script(self) -> None:
        import subprocess

        hook_path = str(
            HOOK_DIR / "invoke_session_initialization_enforcer.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self) -> None:
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(HOOK_DIR / "invoke_session_initialization_enforcer.py")
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
