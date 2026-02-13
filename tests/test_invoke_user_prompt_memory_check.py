"""Tests for invoke_user_prompt_memory_check.py UserPromptSubmit hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks"))

from invoke_user_prompt_memory_check import (
    check_gh_cli_patterns,
    check_planning_keywords,
    check_pr_keywords,
    is_valid_project_root,
    main,
)


class TestIsValidProjectRoot:
    def test_valid_with_git_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        assert is_valid_project_root(str(tmp_path)) is True

    def test_valid_with_settings_json(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        assert is_valid_project_root(str(tmp_path)) is True

    def test_invalid_without_indicators(self, tmp_path: Path) -> None:
        assert is_valid_project_root(str(tmp_path)) is False


class TestCheckPlanningKeywords:
    @pytest.mark.parametrize(
        "prompt",
        [
            "I want to plan the sprint",
            "Please implement the feature",
            "Let's design the API",
            "Can you refactor this code",
            "Add a new endpoint",
            "Update the documentation",
            "Fix the broken test",
            "Create a new module",
        ],
    )
    def test_detects_planning_keywords(self, prompt: str) -> None:
        result = check_planning_keywords(prompt)
        assert result is not None
        assert "ADR-007" in result

    def test_no_match_for_unrelated_prompt(self) -> None:
        assert check_planning_keywords("hello world") is None

    def test_case_insensitive(self) -> None:
        assert check_planning_keywords("PLAN the sprint") is not None


class TestCheckPrKeywords:
    @pytest.mark.parametrize(
        "prompt",
        [
            "create pr for this change",
            "open pr",
            "submit pr now",
            "gh pr create",
            "create pull request",
            "open pull request please",
        ],
    )
    def test_detects_pr_keywords(self, prompt: str) -> None:
        result = check_pr_keywords(prompt)
        assert result is not None
        assert "Pre-PR gate" in result

    def test_no_match_for_unrelated_prompt(self) -> None:
        assert check_pr_keywords("run the tests") is None


class TestCheckGhCliPatterns:
    @pytest.mark.parametrize(
        "prompt,expected_cmd",
        [
            ("run gh pr create", "gh pr create"),
            ("use gh pr list", "gh pr list"),
            ("try gh issue view 123", "gh issue view"),
            ("run gh api repos", "gh api"),
        ],
    )
    def test_detects_gh_cli_commands(self, prompt: str, expected_cmd: str) -> None:
        result = check_gh_cli_patterns(prompt)
        assert result is not None
        assert "Skill-first" in result
        assert expected_cmd in result

    def test_no_match_for_unrelated_prompt(self) -> None:
        assert check_gh_cli_patterns("run the tests") is None


class TestMain:
    def test_returns_zero_when_stdin_is_tty(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        with (
            patch("invoke_user_prompt_memory_check.os.getcwd", return_value=str(tmp_path)),
            patch("sys.stdin") as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_returns_zero_for_invalid_project_root(self, tmp_path: Path) -> None:
        with patch("invoke_user_prompt_memory_check.os.getcwd", return_value=str(tmp_path)):
            assert main() == 0

    def test_returns_zero_for_empty_input(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        with (
            patch("invoke_user_prompt_memory_check.os.getcwd", return_value=str(tmp_path)),
            patch("sys.stdin", StringIO("")),
        ):
            assert main() == 0

    def test_outputs_adr007_for_planning_keywords(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        input_data = json.dumps({"prompt": "implement the new feature"})
        with (
            patch("invoke_user_prompt_memory_check.os.getcwd", return_value=str(tmp_path)),
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "ADR-007" in mock_stdout.getvalue()

    def test_outputs_pre_pr_gate(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        input_data = json.dumps({"prompt": "create pr for the changes"})
        with (
            patch("invoke_user_prompt_memory_check.os.getcwd", return_value=str(tmp_path)),
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "Pre-PR gate" in mock_stdout.getvalue()

    def test_outputs_skill_first_for_gh_cli(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        input_data = json.dumps({"prompt": "run gh pr create --title test"})
        with (
            patch("invoke_user_prompt_memory_check.os.getcwd", return_value=str(tmp_path)),
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "Skill-first" in mock_stdout.getvalue()

    def test_returns_zero_on_json_parse_error(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        with (
            patch("invoke_user_prompt_memory_check.os.getcwd", return_value=str(tmp_path)),
            patch("sys.stdin", StringIO("implement the fix")),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("sys.stderr", new_callable=StringIO) as mock_stderr,
        ):
            result = main()
            assert result == 0
            assert mock_stdout.getvalue() == ""
            assert "JSON parse failed" in mock_stderr.getvalue()

    def test_no_output_for_unrelated_prompt(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        input_data = json.dumps({"prompt": "hello world"})
        with (
            patch("invoke_user_prompt_memory_check.os.getcwd", return_value=str(tmp_path)),
            patch("sys.stdin", StringIO(input_data)),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert mock_stdout.getvalue() == ""
