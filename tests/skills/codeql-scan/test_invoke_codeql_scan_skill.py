#!/usr/bin/env python3
"""Tests for invoke_codeql_scan_skill constants, helpers, and CLI entry point.

run_scan has its own module, test_invoke_codeql_scan_skill_run_scan.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/codeql-scan/scripts/invoke_codeql_scan_skill.py")
get_repo_root = mod.get_repo_root
write_colored = mod.write_colored
main = mod.main
VALID_OPERATIONS = mod.VALID_OPERATIONS
VALID_LANGUAGES = mod.VALID_LANGUAGES


class TestConstants:
    """Tests for module constants."""

    def test_valid_operations(self) -> None:
        assert "full" in VALID_OPERATIONS
        assert "quick" in VALID_OPERATIONS
        assert "validate" in VALID_OPERATIONS

    def test_valid_languages(self) -> None:
        assert "python" in VALID_LANGUAGES
        assert "actions" in VALID_LANGUAGES


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_returns_string_in_git_repo(self, project_root: Path) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=str(project_root))
            result = get_repo_root()
            assert result == str(project_root)

    def test_returns_worktree_top_not_main_checkout(self) -> None:
        """In a linked worktree, repo root is the worktree top (#2373).

        --git-common-dir would return the MAIN checkout's shared .git, so the
        old dirname() logic resolved to the main checkout. --show-toplevel
        returns this worktree's root. Asserts the resolver passes
        --show-toplevel and returns its output verbatim.
        """
        worktree_top = "/repo/.git/worktrees/feat/checkout"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=worktree_top + "\n")
            result = get_repo_root()
            assert result == worktree_top
            assert mock_run.call_args.args[0] == [
                "git",
                "rev-parse",
                "--show-toplevel",
            ]

    def test_returns_none_outside_git_repo(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = get_repo_root()
            assert result is None

    def test_returns_none_on_empty_toplevel(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="   \n")
            result = get_repo_root()
            assert result is None

    @patch("subprocess.run", side_effect=FileNotFoundError())
    def test_returns_none_when_git_missing(self, mock_run: MagicMock) -> None:
        result = get_repo_root()
        assert result is None


class TestWriteColored:
    """Tests for write_colored function."""

    def test_success_prefix(self, capsys: pytest.CaptureFixture[str]) -> None:
        write_colored("test message", "success")
        captured = capsys.readouterr()
        assert "[PASS]" in captured.err
        assert "test message" in captured.err

    def test_error_prefix(self, capsys: pytest.CaptureFixture[str]) -> None:
        write_colored("error message", "error")
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.err

    def test_warning_prefix(self, capsys: pytest.CaptureFixture[str]) -> None:
        write_colored("warning message", "warning")
        captured = capsys.readouterr()
        assert "[WARNING]" in captured.err

    def test_info_prefix(self, capsys: pytest.CaptureFixture[str]) -> None:
        write_colored("info message", "info")
        captured = capsys.readouterr()
        assert "[INFO]" in captured.err


class TestMain:
    """Tests for main entry point."""

    def test_defaults_to_full_operation(self) -> None:
        with patch("sys.argv", ["invoke_codeql_scan_skill.py"]):
            with patch.object(mod, "run_scan", return_value=0) as mock_scan:
                result = main()
        mock_scan.assert_called_once_with(operation="full", languages=None, ci_mode=False)
        assert result == 0

    def test_passes_ci_flag(self) -> None:
        with patch("sys.argv", ["invoke_codeql_scan_skill.py", "--ci"]):
            with patch.object(mod, "run_scan", return_value=0) as mock_scan:
                main()
        mock_scan.assert_called_once_with(operation="full", languages=None, ci_mode=True)

    def test_passes_languages(self) -> None:
        with patch("sys.argv", ["invoke_codeql_scan_skill.py", "--languages", "python"]):
            with patch.object(mod, "run_scan", return_value=0) as mock_scan:
                main()
        mock_scan.assert_called_once_with(operation="full", languages=["python"], ci_mode=False)

    def test_help_exits_zero(self) -> None:
        with patch("sys.argv", ["invoke_codeql_scan_skill.py", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]
