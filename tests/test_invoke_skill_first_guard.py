"""Tests for invoke_skill_first_guard.py PreToolUse hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path for hook imports
_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks" / "PreToolUse"))

from invoke_skill_first_guard import (  # noqa: E402
    find_skill_script,
    main,
    parse_gh_command,
)


class TestParseGhCommand:
    def test_parses_simple_gh_command(self) -> None:
        result = parse_gh_command("gh pr view 123")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "view"
        assert result["full_command"] == "gh pr view 123"

    def test_parses_gh_issue_create(self) -> None:
        result = parse_gh_command("gh issue create --title test")
        assert result is not None
        assert result["operation"] == "issue"
        assert result["action"] == "create"

    def test_returns_none_for_non_gh_command(self) -> None:
        assert parse_gh_command("git commit -m test") is None

    def test_returns_none_for_empty_string(self) -> None:
        assert parse_gh_command("") is None

    def test_returns_none_for_partial_gh_command(self) -> None:
        assert parse_gh_command("gh") is None

    def test_handles_gh_in_middle_of_command(self) -> None:
        result = parse_gh_command("echo hello && gh pr list")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "list"


class TestFindSkillScript:
    def test_exact_match_found(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        (script_dir / "get_pr_context.py").write_text("# skill", encoding="utf-8")

        result = find_skill_script("pr", "view", str(tmp_path))
        assert result is not None
        assert "get_pr_context.py" in result["path"]

    def test_exact_match_not_on_disk(self, tmp_path: Path) -> None:
        # Mapping exists but file does not
        result = find_skill_script("pr", "view", str(tmp_path))
        assert result is None

    def test_fuzzy_match_found(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        (script_dir / "custom_review.py").write_text("# skill", encoding="utf-8")

        # "review" action doesn't have exact mapping, fuzzy finds file containing "review"
        result = find_skill_script("pr", "review", str(tmp_path))
        assert result is not None

    def test_no_match_when_dir_missing(self, tmp_path: Path) -> None:
        result = find_skill_script("workflow", "run", str(tmp_path))
        assert result is None

    def test_no_match_for_unmapped_action(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        # No file matching "nonexistent"
        result = find_skill_script("pr", "nonexistent", str(tmp_path))
        assert result is None


class TestMainAllowPath:
    @patch("invoke_skill_first_guard.sys.stdin")
    def test_allows_when_tty(self, mock_stdin: MagicMock) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_skill_first_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_empty_stdin(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_skill_first_guard.sys.stdin", new_callable=StringIO)
    def test_allows_non_gh_commands(self, mock_stdin: StringIO) -> None:
        data = json.dumps({"tool_input": {"command": "git commit -m test"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_skill_first_guard.find_skill_script", return_value=None)
    @patch("invoke_skill_first_guard.get_project_directory", return_value="/tmp")
    @patch("invoke_skill_first_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_no_skill_exists(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_skill: MagicMock,
    ) -> None:
        data = json.dumps({"tool_input": {"command": "gh workflow run deploy"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainBlockPath:
    @patch("invoke_skill_first_guard.find_skill_script")
    @patch("invoke_skill_first_guard.get_project_directory", return_value="/tmp")
    @patch("invoke_skill_first_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_when_skill_exists(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        mock_skill: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_skill.return_value = {
            "path": "/tmp/.claude/skills/github/scripts/pr/get_pr_context.py",
            "example": (
                "python3 .claude/skills/github/scripts/pr/"
                "get_pr_context.py --pull-request 123"
            ),
        }
        data = json.dumps({"tool_input": {"command": "gh pr view 123"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
            captured = capsys.readouterr()
            assert "BLOCKED" in captured.out


class TestMainFailOpen:
    @patch("invoke_skill_first_guard.parse_gh_command", side_effect=Exception("boom"))
    @patch("invoke_skill_first_guard.sys.stdin", new_callable=StringIO)
    def test_failopen_on_exception(
        self,
        mock_stdin: StringIO,
        _mock_parse: MagicMock,
    ) -> None:
        data = json.dumps({"tool_input": {"command": "gh pr view 123"}})
        mock_stdin.write(data)
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0
