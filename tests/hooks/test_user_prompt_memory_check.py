"""Tests for invoke_user_prompt_memory_check.py Claude Code UserPromptSubmit hook."""

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

import invoke_user_prompt_memory_check  # noqa: E402


class TestIsValidProjectRoot:
    """Tests for is_valid_project_root."""

    def test_valid_with_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert invoke_user_prompt_memory_check.is_valid_project_root(str(tmp_path)) is True

    def test_valid_with_claude_settings(self, tmp_path):
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "settings.json").write_text("{}")
        assert invoke_user_prompt_memory_check.is_valid_project_root(str(tmp_path)) is True

    def test_invalid_no_indicators(self, tmp_path):
        assert invoke_user_prompt_memory_check.is_valid_project_root(str(tmp_path)) is False


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("invoke_user_prompt_memory_check.skip_if_consumer_repo", return_value=False):
        yield


class TestPlanningKeywords:
    """Tests for planning keyword detection."""

    def test_detects_plan_keyword(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "Please plan the new feature"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        invoke_user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007" in captured.out

    def test_detects_implement_keyword(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "implement the auth module"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        invoke_user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007" in captured.out

    def test_no_keyword_no_output(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "hello world"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        invoke_user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007" not in captured.out

    def test_case_insensitive(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "REFACTOR the module"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        invoke_user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "ADR-007" in captured.out


class TestPRKeywords:
    """Tests for PR creation keyword detection."""

    def test_detects_create_pr(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "create pr for the changes"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        invoke_user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Pre-PR" in captured.out or "pre-PR" in captured.out.lower()

    def test_detects_open_pull_request(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "open pull request"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        invoke_user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Pre-PR" in captured.out or "pre-PR" in captured.out.lower()


class TestGHCLIPatterns:
    """Tests for GitHub CLI skill suggestion."""

    def test_detects_gh_issue_view(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "use gh issue view 123"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        invoke_user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Skill" in captured.out or "skill" in captured.out.lower()

    def test_detects_gh_api(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "run gh api repos/..."})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        invoke_user_prompt_memory_check.main()
        captured = capsys.readouterr()
        assert "Skill" in captured.out or "skill" in captured.out.lower()


class TestMain:
    """Tests for main() entry point."""

    def test_invalid_project_root_fails_open(self, monkeypatch, tmp_path):
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        assert invoke_user_prompt_memory_check.main() == 0

    def test_always_returns_zero(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"prompt": "plan something"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        assert invoke_user_prompt_memory_check.main() == 0

    def test_handles_invalid_json_input(self, monkeypatch, tmp_path):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("not valid json"))
        assert invoke_user_prompt_memory_check.main() == 0

    def test_handles_json_without_prompt(self, monkeypatch, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        input_data = json.dumps({"other_field": "value"})
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        result = invoke_user_prompt_memory_check.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR-007" not in captured.out


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_user_prompt_memory_check_as_script(self):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "invoke_user_prompt_memory_check.py"
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
            / ".claude" / "hooks" / "invoke_user_prompt_memory_check.py"
        )
        (tmp_path / ".git").mkdir()
        monkeypatch.setattr("os.getcwd", lambda: str(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt": "hello"}'))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
