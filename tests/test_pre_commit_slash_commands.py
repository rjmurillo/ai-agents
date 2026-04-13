"""Tests for pre_commit_slash_commands.py git pre-commit hook."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))

from pre_commit_slash_commands import (
    get_staged_slash_commands,
    main,
    validate_file,
)


class TestGetStagedSlashCommands:
    def test_returns_matching_files(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ".claude/commands/test.md\n.claude/commands/other.md\nsrc/main.py\n"
        with patch("pre_commit_slash_commands.subprocess.run", return_value=mock_result):
            files = get_staged_slash_commands()
            assert files == [".claude/commands/test.md", ".claude/commands/other.md"]

    def test_returns_empty_for_no_matching_files(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/main.py\nREADME.md\n"
        with patch("pre_commit_slash_commands.subprocess.run", return_value=mock_result):
            files = get_staged_slash_commands()
            assert files == []

    def test_returns_empty_on_git_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        with patch("pre_commit_slash_commands.subprocess.run", return_value=mock_result):
            files = get_staged_slash_commands()
            assert files == []

    def test_filters_non_md_files(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ".claude/commands/test.md\n.claude/commands/script.py\n"
        with patch("pre_commit_slash_commands.subprocess.run", return_value=mock_result):
            files = get_staged_slash_commands()
            assert files == [".claude/commands/test.md"]

    def test_handles_empty_git_output(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("pre_commit_slash_commands.subprocess.run", return_value=mock_result):
            files = get_staged_slash_commands()
            assert files == []


class TestValidateFile:
    def test_returns_true_on_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("pre_commit_slash_commands.subprocess.run", return_value=mock_result):
            assert validate_file("test.md") is True

    def test_returns_false_on_failure(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("pre_commit_slash_commands.subprocess.run", return_value=mock_result):
            assert validate_file("test.md") is False


class TestMain:
    def test_skips_when_no_files_staged(self) -> None:
        with patch("pre_commit_slash_commands.get_staged_slash_commands", return_value=[]):
            assert main() == 0

    def test_passes_when_all_valid(self) -> None:
        with (
            patch(
                "pre_commit_slash_commands.get_staged_slash_commands",
                return_value=[".claude/commands/a.md", ".claude/commands/b.md"],
            ),
            patch("pre_commit_slash_commands.validate_file", return_value=True),
        ):
            assert main() == 0

    def test_fails_when_any_invalid(self) -> None:
        with (
            patch(
                "pre_commit_slash_commands.get_staged_slash_commands",
                return_value=[".claude/commands/a.md", ".claude/commands/b.md"],
            ),
            patch(
                "pre_commit_slash_commands.validate_file",
                side_effect=[True, False],
            ),
        ):
            assert main() == 1

    def test_reports_failed_files(self) -> None:
        from io import StringIO

        with (
            patch(
                "pre_commit_slash_commands.get_staged_slash_commands",
                return_value=[".claude/commands/bad.md"],
            ),
            patch("pre_commit_slash_commands.validate_file", return_value=False),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 1
            output = mock_stdout.getvalue()
            assert "FAIL" in output
            assert "bad.md" in output

    def test_reports_all_passed(self) -> None:
        from io import StringIO

        with (
            patch(
                "pre_commit_slash_commands.get_staged_slash_commands",
                return_value=[".claude/commands/good.md"],
            ),
            patch("pre_commit_slash_commands.validate_file", return_value=True),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "PASS" in mock_stdout.getvalue()
