"""Tests for PreToolUse skill_first_guard hook.

Verifies that raw gh commands are blocked when a validated skill script exists,
and allowed when no skill exists for the operation.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
sys.path.insert(0, str(HOOK_DIR))

from skill_first_guard import (  # noqa: E402
    SKILL_MAPPINGS,
    format_block_response,
    get_project_directory,
    get_skill_script,
    main,
    parse_gh_command,
)


class TestParseGhCommand:
    """Tests for gh command parsing."""

    def test_pr_create(self) -> None:
        result = parse_gh_command("gh pr create --title test")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "create"

    def test_issue_list(self) -> None:
        result = parse_gh_command("gh issue list")
        assert result is not None
        assert result["operation"] == "issue"
        assert result["action"] == "list"

    def test_not_gh_command(self) -> None:
        assert parse_gh_command("git push origin main") is None

    def test_empty_string(self) -> None:
        assert parse_gh_command("") is None

    def test_whitespace_only(self) -> None:
        assert parse_gh_command("   ") is None

    def test_gh_with_pipe(self) -> None:
        result = parse_gh_command("gh pr view 123 | head")
        assert result is not None
        assert result["operation"] == "pr"
        assert result["action"] == "view"

    def test_gh_single_word(self) -> None:
        """gh with only operation and no action should not match."""
        assert parse_gh_command("gh auth") is None

    def test_preserves_full_command(self) -> None:
        cmd = "gh pr merge 123 --squash"
        result = parse_gh_command(cmd)
        assert result is not None
        assert result["full_command"] == cmd


class TestGetSkillScript:
    """Tests for skill script lookup."""

    def test_exact_mapping_found(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        script_file = script_dir / "get_pr_context.py"
        script_file.write_text("# stub")

        result = get_skill_script("pr", "view", str(tmp_path))
        assert result is not None
        assert result["path"] == str(script_file)

    def test_exact_mapping_script_missing(self, tmp_path: Path) -> None:
        """Mapping exists but file doesn't. Should return None."""
        result = get_skill_script("pr", "view", str(tmp_path))
        assert result is None

    def test_no_mapping(self, tmp_path: Path) -> None:
        result = get_skill_script("release", "create", str(tmp_path))
        assert result is None

    def test_fuzzy_match(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        script_file = script_dir / "get_pr_reviews.py"
        script_file.write_text("# stub")

        result = get_skill_script("pr", "reviews", str(tmp_path))
        assert result is not None
        assert "get_pr_reviews.py" in result["path"]

    def test_fuzzy_no_match(self, tmp_path: Path) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)

        result = get_skill_script("pr", "nonexistent", str(tmp_path))
        assert result is None

    def test_unknown_operation_no_dir(self, tmp_path: Path) -> None:
        result = get_skill_script("unknown", "action", str(tmp_path))
        assert result is None


class TestFormatBlockResponse:
    """Tests for block response formatting."""

    def test_contains_blocked_command(self) -> None:
        output = format_block_response("gh pr create", "/path/to/skill", "python3 skill.py")
        assert "gh pr create" in output
        assert "BLOCKED" in output

    def test_contains_example(self) -> None:
        output = format_block_response("gh pr view 1", "/path", "python3 skill.py --pr 1")
        assert "python3 skill.py --pr 1" in output


class TestGetProjectDirectory:
    """Tests for project directory resolution."""

    def test_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/my/project")
        assert get_project_directory() == "/my/project"

    def test_git_walk_up(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)
        assert get_project_directory() == str(tmp_path)


class TestSkillMappings:
    """Tests for skill mapping constants."""

    def test_pr_operations_exist(self) -> None:
        assert "pr" in SKILL_MAPPINGS
        assert len(SKILL_MAPPINGS["pr"]) >= 5

    def test_issue_operations_exist(self) -> None:
        assert "issue" in SKILL_MAPPINGS
        assert len(SKILL_MAPPINGS["issue"]) >= 3


class TestMainAllow:
    """Tests for main() allowing commands."""

    def test_tty_stdin(self) -> None:
        with patch("skill_first_guard.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    def test_non_gh_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"command": "ls -la"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_no_tool_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_name": "Bash"})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_no_command_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"file_path": "/some/file"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_gh_command_no_skill(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "gh release create v1.0"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_invalid_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert main() == 0


class TestMainBlock:
    """Tests for main() blocking commands."""

    def test_blocks_gh_pr_view_with_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        (script_dir / "get_pr_context.py").write_text("# stub")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "gh pr view 123"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        result = main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "Raw GitHub Command" in captured.out

    def test_blocks_gh_pr_create_with_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        script_dir.mkdir(parents=True)
        (script_dir / "new_pr.py").write_text("# stub")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "gh pr create --title test"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        assert main() == 2

    def test_blocks_gh_issue_view_with_skill(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        script_dir = tmp_path / ".claude" / "skills" / "github" / "scripts" / "issue"
        script_dir.mkdir(parents=True)
        (script_dir / "get_issue_context.py").write_text("# stub")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"tool_input": {"command": "gh issue view 456"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        assert main() == 2
