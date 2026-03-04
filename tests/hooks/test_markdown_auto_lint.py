"""Tests for PostToolUse invoke_markdown_auto_lint hook.

Verifies that markdown files are linted after write/edit operations,
non-markdown files are skipped, and errors are handled gracefully.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PostToolUse"
sys.path.insert(0, str(HOOK_DIR))

from invoke_markdown_auto_lint import (  # noqa: E402
    get_file_path_from_input,
    get_project_directory,
    main,
    should_lint_file,
)


class TestGetFilePathFromInput:
    """Tests for file path extraction."""

    def test_extracts_file_path(self) -> None:
        hook_input = {"tool_input": {"file_path": "/path/to/file.md"}}
        assert get_file_path_from_input(hook_input) == "/path/to/file.md"

    def test_no_tool_input(self) -> None:
        assert get_file_path_from_input({}) is None

    def test_tool_input_not_dict(self) -> None:
        assert get_file_path_from_input({"tool_input": "string"}) is None

    def test_no_file_path_key(self) -> None:
        assert get_file_path_from_input({"tool_input": {"command": "ls"}}) is None


class TestGetProjectDirectory:
    """Tests for project directory resolution."""

    def test_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/my/project")
        result = get_project_directory({"cwd": "/other"})
        assert result == "/my/project"

    def test_cwd_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = get_project_directory({"cwd": "/some/dir"})
        assert result == "/some/dir"

    def test_no_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = get_project_directory({})
        assert result  # Falls back to os.getcwd()


class TestShouldLintFile:
    """Tests for lint eligibility check."""

    def test_md_file_exists(self, tmp_path: Path) -> None:
        md = tmp_path / "test.md"
        md.write_text("# Hello")
        assert should_lint_file(str(md), str(tmp_path)) is True

    def test_md_file_uppercase(self, tmp_path: Path) -> None:
        md = tmp_path / "README.MD"
        md.write_text("# Hello")
        assert should_lint_file(str(md), str(tmp_path)) is True

    def test_non_md_file(self, tmp_path: Path) -> None:
        py = tmp_path / "test.py"
        py.write_text("# hello")
        assert should_lint_file(str(py), str(tmp_path)) is False

    def test_ps1_file_rejected(self, tmp_path: Path) -> None:
        assert should_lint_file("/some/script.ps1", str(tmp_path)) is False

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        assert should_lint_file(str(tmp_path / "nonexistent.md"), str(tmp_path)) is False

    def test_empty_path(self, tmp_path: Path) -> None:
        assert should_lint_file("", str(tmp_path)) is False

    def test_none_path(self, tmp_path: Path) -> None:
        assert should_lint_file(None, str(tmp_path)) is False

    def test_whitespace_path(self, tmp_path: Path) -> None:
        assert should_lint_file("   ", str(tmp_path)) is False


class TestMainAllow:
    """Tests for main() non-blocking behavior."""

    def test_tty_stdin(self) -> None:
        with patch("invoke_markdown_auto_lint.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    def test_non_md_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        data = json.dumps({"tool_input": {"file_path": "/some/file.py"}})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_invalid_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert main() == 0

    def test_md_file_triggers_lint(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        md = tmp_path / "test.md"
        md.write_text("# Hello")

        data = json.dumps({"tool_input": {"file_path": str(md)}, "cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("invoke_markdown_auto_lint.subprocess.run", return_value=mock_result):
            assert main() == 0

    def test_invalid_json_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Invalid JSON input returns 0 (fail-open)."""
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        assert main() == 0
