"""Tests for invoke_markdown_auto_lint.py PostToolUse hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "PostToolUse"))

from invoke_markdown_auto_lint import (
    get_file_path_from_input,
    get_project_directory,
    main,
    should_lint_file,
)


class TestGetFilePathFromInput:
    def test_extracts_file_path(self) -> None:
        hook_input: dict[str, object] = {"tool_input": {"file_path": "/tmp/test.md"}}
        assert get_file_path_from_input(hook_input) == "/tmp/test.md"

    def test_returns_none_for_missing_tool_input(self) -> None:
        assert get_file_path_from_input({}) is None

    def test_returns_none_for_missing_file_path(self) -> None:
        assert get_file_path_from_input({"tool_input": {}}) is None

    def test_returns_none_for_empty_file_path(self) -> None:
        assert get_file_path_from_input({"tool_input": {"file_path": "  "}}) is None

    def test_strips_whitespace(self) -> None:
        hook_input: dict[str, object] = {"tool_input": {"file_path": "  /tmp/test.md  "}}
        assert get_file_path_from_input(hook_input) == "/tmp/test.md"

    def test_returns_none_for_non_dict_tool_input(self) -> None:
        assert get_file_path_from_input({"tool_input": "not a dict"}) is None


class TestGetProjectDirectory:
    def test_uses_env_var_when_set(self) -> None:
        with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": "/env/project"}):
            assert get_project_directory({}) == "/env/project"

    def test_uses_cwd_from_hook_input(self) -> None:
        with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": ""}):
            assert get_project_directory({"cwd": "/hook/cwd"}) == "/hook/cwd"

    def test_falls_back_to_getcwd(self) -> None:
        with (
            patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": ""}),
            patch("os.getcwd", return_value="/fallback"),
        ):
            assert get_project_directory({}) == "/fallback"


class TestShouldLintFile:
    def test_returns_false_for_none(self) -> None:
        assert should_lint_file(None) is False

    def test_returns_false_for_empty(self) -> None:
        assert should_lint_file("") is False

    def test_returns_false_for_non_md_file(self) -> None:
        assert should_lint_file("/tmp/test.py") is False

    def test_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        assert should_lint_file(str(tmp_path / "nonexistent.md")) is False

    def test_returns_true_for_existing_md_file(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello", encoding="utf-8")
        assert should_lint_file(str(md_file)) is True

    def test_case_insensitive_extension(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.MD"
        md_file.write_text("# Hello", encoding="utf-8")
        assert should_lint_file(str(md_file)) is True


class TestMain:
    def test_returns_zero_when_stdin_is_tty(self) -> None:
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_returns_zero_for_empty_input(self) -> None:
        with patch("sys.stdin", StringIO("")):
            assert main() == 0

    def test_returns_zero_for_invalid_json(self) -> None:
        with patch("sys.stdin", StringIO("not json")):
            assert main() == 0

    def test_returns_zero_for_non_md_file(self) -> None:
        input_data = json.dumps({"tool_input": {"file_path": "/tmp/test.py"}})
        with patch("sys.stdin", StringIO(input_data)):
            assert main() == 0

    def test_runs_linter_on_md_file(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello", encoding="utf-8")
        input_data = json.dumps(
            {
                "tool_input": {"file_path": str(md_file)},
                "cwd": str(tmp_path),
            }
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": ""}),
            patch("invoke_markdown_auto_lint.subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = main()
            assert result == 0
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert "markdownlint-cli2" in call_args[0][0]
            assert "--fix" in call_args[0][0]

    def test_handles_linter_failure_with_output(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello", encoding="utf-8")
        input_data = json.dumps(
            {
                "tool_input": {"file_path": str(md_file)},
                "cwd": str(tmp_path),
            }
        )
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "MD013/line-length: some error"
        mock_result.stdout = ""
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": ""}),
            patch("invoke_markdown_auto_lint.subprocess.run", return_value=mock_result),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "WARNING" in mock_stdout.getvalue()

    def test_handles_linter_failure_no_output(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello", encoding="utf-8")
        input_data = json.dumps(
            {
                "tool_input": {"file_path": str(md_file)},
                "cwd": str(tmp_path),
            }
        )
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = ""
        mock_result.stdout = ""
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": ""}),
            patch("invoke_markdown_auto_lint.subprocess.run", return_value=mock_result),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "Linter failed with no output" in mock_stdout.getvalue()

    def test_handles_npx_not_found(self, tmp_path: Path) -> None:
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello", encoding="utf-8")
        input_data = json.dumps(
            {
                "tool_input": {"file_path": str(md_file)},
                "cwd": str(tmp_path),
            }
        )
        with (
            patch("sys.stdin", StringIO(input_data)),
            patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": ""}),
            patch(
                "invoke_markdown_auto_lint.subprocess.run",
                side_effect=FileNotFoundError("npx not found"),
            ),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
        ):
            result = main()
            assert result == 0
            assert "npx not found" in mock_stdout.getvalue()
