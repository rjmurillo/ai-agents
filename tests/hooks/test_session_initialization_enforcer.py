"""Tests for SessionStart session_initialization_enforcer hook.

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

from session_initialization_enforcer import (  # noqa: E402
    PROTECTED_BRANCHES,
    format_protected_branch_warning,
    format_session_status,
    get_current_branch,
    get_git_status,
    get_project_directory,
    get_recent_commits,
    get_today_session_log,
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

    def test_whitespace(self) -> None:
        assert is_protected_branch("   ") is False

    def test_main_with_whitespace(self) -> None:
        assert is_protected_branch("  main  ") is True


class TestGetProjectDirectory:
    """Tests for project directory resolution."""

    def test_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/my/project")
        assert get_project_directory() == "/my/project"

    def test_git_walk_up(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert get_project_directory() == str(tmp_path)

    def test_fallback_to_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        result = get_project_directory()
        assert os.path.isabs(result)


class TestGetCurrentBranch:
    """Tests for git branch detection."""

    def test_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "feat/my-feature\n"
        with patch("session_initialization_enforcer.subprocess.run", return_value=mock_result):
            assert get_current_branch() == "feat/my-feature"

    def test_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        with patch("session_initialization_enforcer.subprocess.run", return_value=mock_result):
            assert get_current_branch() is None

    def test_git_not_found(self) -> None:
        with patch(
            "session_initialization_enforcer.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert get_current_branch() is None

    def test_timeout(self) -> None:
        with patch(
            "session_initialization_enforcer.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 10),
        ):
            assert get_current_branch() is None


class TestGetGitStatus:
    """Tests for git status retrieval."""

    def test_success_with_changes(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " M file.py\n?? new.py\n"
        with patch("session_initialization_enforcer.subprocess.run", return_value=mock_result):
            result = get_git_status()
        assert "file.py" in result

    def test_clean(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("session_initialization_enforcer.subprocess.run", return_value=mock_result):
            assert get_git_status() == "(clean)"

    def test_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("session_initialization_enforcer.subprocess.run", return_value=mock_result):
            assert "unable" in get_git_status()

    def test_error(self) -> None:
        with patch(
            "session_initialization_enforcer.subprocess.run",
            side_effect=OSError("error"),
        ):
            assert "unable" in get_git_status()


class TestGetRecentCommits:
    """Tests for recent commit retrieval."""

    def test_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 feat: something\ndef5678 fix: other\n"
        with patch("session_initialization_enforcer.subprocess.run", return_value=mock_result):
            result = get_recent_commits()
        assert "abc1234" in result

    def test_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("session_initialization_enforcer.subprocess.run", return_value=mock_result):
            assert "unable" in get_recent_commits()

    def test_custom_count(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 commit"
        with patch(
            "session_initialization_enforcer.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            get_recent_commits(5)
            args = mock_run.call_args[0][0]
            assert "-n" in args
            assert "5" in args

    def test_git_not_found(self) -> None:
        with patch(
            "session_initialization_enforcer.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            assert "unable" in get_recent_commits()

    def test_oserror(self) -> None:
        with patch(
            "session_initialization_enforcer.subprocess.run",
            side_effect=OSError("io error"),
        ):
            assert "unable" in get_recent_commits()


class TestGetTodaySessionLog:
    """Tests for session log discovery."""

    def test_no_directory(self, tmp_path: Path) -> None:
        assert get_today_session_log(str(tmp_path / "nonexistent")) is None

    def test_no_logs(self, tmp_path: Path) -> None:
        with patch("session_initialization_enforcer.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            assert get_today_session_log(str(tmp_path)) is None

    def test_finds_log(self, tmp_path: Path) -> None:
        log = tmp_path / "2026-03-01-session-01.json"
        log.write_text('{"test": true}')
        with patch("session_initialization_enforcer.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            result = get_today_session_log(str(tmp_path))
        assert result == "2026-03-01-session-01.json"


class TestFormatProtectedBranchWarning:
    """Tests for branch warning formatting."""

    def test_contains_branch_name(self) -> None:
        output = format_protected_branch_warning("main")
        assert "main" in output
        assert "WARNING" in output

    def test_contains_git_checkout(self) -> None:
        output = format_protected_branch_warning("master")
        assert "git checkout" in output

    def test_contains_skill_reminder(self) -> None:
        output = format_protected_branch_warning("main")
        assert "Skill-First" in output


class TestFormatSessionStatus:
    """Tests for session status formatting."""

    def test_with_session_log(self) -> None:
        output = format_session_status(
            "feat/branch", "2026-03-01-session-01.json", "M file.py", "abc1234 commit"
        )
        assert "feat/branch" in output
        assert "Session log exists" in output
        assert "Continue with work" in output

    def test_without_session_log(self) -> None:
        output = format_session_status(
            "feat/branch", None, "(clean)", "abc1234 commit"
        )
        assert "No session log" in output
        assert "Create session log" in output

    def test_contains_git_state(self) -> None:
        output = format_session_status(
            "dev", "log.json", "M foo.py\n?? bar.py", "abc fix"
        )
        assert "foo.py" in output
        assert "bar.py" in output
        assert "abc fix" in output


class TestProtectedBranches:
    """Tests for the constant."""

    def test_contains_main_and_master(self) -> None:
        assert "main" in PROTECTED_BRANCHES
        assert "master" in PROTECTED_BRANCHES


class TestMainProtectedBranch:
    """Tests for main() on protected branch."""

    def test_main_branch_warning(self, capsys: pytest.CaptureFixture) -> None:
        mod = "session_initialization_enforcer"
        with patch(f"{mod}.get_project_directory", return_value="/project"):
            with patch(f"{mod}.get_current_branch", return_value="main"):
                assert main() == 0

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "Protected Branch" in captured.out


class TestMainFeatureBranch:
    """Tests for main() on feature branch."""

    def test_feature_branch_status(self, capsys: pytest.CaptureFixture) -> None:
        mod = "session_initialization_enforcer"
        with patch(f"{mod}.get_project_directory", return_value="/project"):
            with patch(f"{mod}.get_current_branch", return_value="feat/test"):
                with patch(f"{mod}.get_git_status", return_value="(clean)"):
                    with patch(
                        f"{mod}.get_recent_commits",
                        return_value="abc commit",
                    ):
                        with patch(
                            f"{mod}.get_today_session_log",
                            return_value=None,
                        ):
                            assert main() == 0

        captured = capsys.readouterr()
        assert "Session Initialization Status" in captured.out
        assert "feat/test" in captured.out

    def test_with_session_log(self, capsys: pytest.CaptureFixture) -> None:
        mod = "session_initialization_enforcer"
        with patch(f"{mod}.get_project_directory", return_value="/project"):
            with patch(f"{mod}.get_current_branch", return_value="dev"):
                with patch(f"{mod}.get_git_status", return_value="M file"):
                    with patch(
                        f"{mod}.get_recent_commits",
                        return_value="abc",
                    ):
                        with patch(
                            f"{mod}.get_today_session_log",
                            return_value="2026-03-01-session-01.json",
                        ):
                            assert main() == 0

        captured = capsys.readouterr()
        assert "Session log exists" in captured.out


class TestMainErrorHandling:
    """Tests for main() error handling."""

    def test_exception_fails_open(self) -> None:
        with patch(
            "session_initialization_enforcer.get_project_directory",
            side_effect=RuntimeError("boom"),
        ):
            assert main() == 0

    def test_none_branch(self, capsys: pytest.CaptureFixture) -> None:
        mod = "session_initialization_enforcer"
        with patch(f"{mod}.get_project_directory", return_value="/p"):
            with patch(f"{mod}.get_current_branch", return_value=None):
                with patch(f"{mod}.get_git_status", return_value="(clean)"):
                    with patch(
                        f"{mod}.get_recent_commits",
                        return_value="abc",
                    ):
                        with patch(
                            f"{mod}.get_today_session_log",
                            return_value=None,
                        ):
                            assert main() == 0

        captured = capsys.readouterr()
        assert "(unknown)" in captured.out


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_session_initialization_enforcer_as_script(self) -> None:
        import subprocess

        hook_path = str(
            HOOK_DIR / "session_initialization_enforcer.py"
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

        hook_path = str(HOOK_DIR / "session_initialization_enforcer.py")
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
