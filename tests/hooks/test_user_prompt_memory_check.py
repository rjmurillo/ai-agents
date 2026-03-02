"""Tests for user_prompt_memory_check.py Claude Code UserPromptSubmit hook."""

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for import
HOOKS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import user_prompt_memory_check


class TestIsValidProjectRoot:
    """Tests for _is_valid_project_root."""

    def test_valid_with_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert user_prompt_memory_check._is_valid_project_root(str(tmp_path)) is True

    def test_valid_with_claude_settings(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        assert user_prompt_memory_check._is_valid_project_root(str(tmp_path)) is True

    def test_invalid_no_indicators(self, tmp_path):
        assert user_prompt_memory_check._is_valid_project_root(str(tmp_path)) is False


class TestPlanningKeywords:
    """Tests for planning keyword detection."""

    def test_detects_plan_keyword(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "Please plan the new feature"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007 Memory Check" in captured.out

    def test_detects_implement_keyword(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "implement the auth module"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007 Memory Check" in captured.out

    def test_no_keyword_no_output(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "hello world"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007 Memory Check" not in captured.out

    def test_case_insensitive(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "REFACTOR the module"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007 Memory Check" in captured.out

    def test_word_boundary_matching(self, monkeypatch, tmp_path, capsys):
        """'planned' should not match 'plan' due to word boundary."""
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "the airplane was planned"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        # 'planned' does not match '\bplan\b' but 'add' or other words might
        # Actually 'planned' won't match '\bplan\b' since it's 'planned'
        # But the prompt has no exact keyword match
        # This test verifies word boundary works
        assert "ADR-007 Memory Check" not in captured.out


class TestPRKeywords:
    """Tests for PR creation keyword detection."""

    def test_detects_create_pr(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "create pr for the changes"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Pre-PR Validation Gate" in captured.out

    def test_detects_open_pull_request(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "open pull request"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Pre-PR Validation Gate" in captured.out

    def test_no_pr_keyword_no_output(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "check the status"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Pre-PR Validation Gate" not in captured.out


class TestGHCLIPatterns:
    """Tests for GitHub CLI skill suggestion."""

    def test_detects_gh_issue_view(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "use gh issue view 123"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Skill Usage Check" in captured.out

    def test_detects_gh_api(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "run gh api repos/..."})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Skill Usage Check" in captured.out

    def test_no_gh_cli_no_output(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "just a normal message"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Skill Usage Check" not in captured.out


class TestMain:
    """Tests for main() entry point."""

    def test_invalid_project_root_fails_open(self, monkeypatch, tmp_path):
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        assert user_prompt_memory_check.main() == 0

    def test_always_returns_zero(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "plan something"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert user_prompt_memory_check.main() == 0

    def test_handles_invalid_json_input(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("not valid json"))
        assert user_prompt_memory_check.main() == 0

    def test_handles_json_without_prompt(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"other_field": "value"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        result = user_prompt_memory_check.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR-007 Memory Check" not in captured.out

    def test_multiple_matches_all_output(self, monkeypatch, tmp_path, capsys):
        """Prompt matching both planning and PR keywords outputs both."""
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "create pr for the fix"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        # 'create' matches planning, 'create pr' matches PR
        assert "ADR-007 Memory Check" in captured.out
        assert "Pre-PR Validation Gate" in captured.out

    def test_raw_text_fallback_on_json_error(self, monkeypatch, tmp_path, capsys):
        """When JSON parsing fails, raw text is used for matching."""
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        # Send raw text that matches planning keyword
        monkeypatch.setattr("sys.stdin", io.StringIO("implement something"))
        user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007 Memory Check" in captured.out


class TestMainBranches:
    """Branch coverage for main() edge cases."""

    def test_json_parses_to_non_dict(self, monkeypatch, tmp_path, capsys):
        """When JSON parses to a non-dict (list), prompt_text stays empty."""
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps(["not", "a", "dict"])
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        result = user_prompt_memory_check.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR-007 Memory Check" not in captured.out


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_user_prompt_memory_check_as_script(self):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "user_prompt_memory_check.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input='{"prompt": "hello"}',
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self, monkeypatch, tmp_path):
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "user_prompt_memory_check.py"
        )
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "hello"}'))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
