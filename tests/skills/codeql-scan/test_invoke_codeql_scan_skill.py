#!/usr/bin/env python3
"""Tests for invoke_codeql_scan_skill module."""

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
run_scan = mod.run_scan
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

    def test_returns_none_outside_git_repo(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            result = get_repo_root()
            assert result is None

    @patch("subprocess.run", side_effect=FileNotFoundError())
    def test_returns_none_when_git_missing(self, mock_run: MagicMock) -> None:
        result = get_repo_root()
        assert result is None


class TestWriteColored:
    """Tests for write_colored function."""

    def test_success_prefix(self, capsys: pytest.CaptureFixture) -> None:
        write_colored("test message", "success")
        captured = capsys.readouterr()
        assert "[PASS]" in captured.err

    def test_error_prefix(self, capsys: pytest.CaptureFixture) -> None:
        write_colored("error message", "error")
        captured = capsys.readouterr()
        assert "[FAIL]" in captured.err

    def test_warning_prefix(self, capsys: pytest.CaptureFixture) -> None:
        write_colored("warning message", "warning")
        captured = capsys.readouterr()
        assert "[WARNING]" in captured.err

    def test_info_prefix(self, capsys: pytest.CaptureFixture) -> None:
        write_colored("info message", "info")
        captured = capsys.readouterr()
        assert "[INFO]" in captured.err


class TestRunScan:
    """Tests for run_scan function."""

    def test_returns_3_when_not_in_repo(self) -> None:
        with patch.object(mod, "get_repo_root", return_value=None):
            result = run_scan()
        assert result == 3

    def test_validate_returns_3_when_config_missing(self, tmp_path: Path) -> None:
        with patch.object(mod, "get_repo_root", return_value=str(tmp_path)):
            result = run_scan(operation="validate")
        assert result == 3

    def test_returns_3_when_codeql_cli_missing(self, tmp_path: Path) -> None:
        with patch.object(mod, "get_repo_root", return_value=str(tmp_path)):
            result = run_scan(operation="full")
        assert result == 3

    def test_returns_3_when_scan_script_missing(self, tmp_path: Path) -> None:
        codeql_dir = tmp_path / ".codeql" / "cli"
        codeql_dir.mkdir(parents=True)
        (codeql_dir / "codeql").touch()
        with patch.object(mod, "get_repo_root", return_value=str(tmp_path)):
            result = run_scan(operation="full")
        assert result == 3


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


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]
