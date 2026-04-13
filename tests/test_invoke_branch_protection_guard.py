"""Tests for invoke_branch_protection_guard.py PreToolUse hook."""

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

from invoke_branch_protection_guard import (  # noqa: E402
    PROTECTED_BRANCHES,
    get_working_directory,
    main,
    write_block_response,
)


class TestWriteBlockResponse:
    def test_outputs_json_with_block_decision(self, capsys: pytest.CaptureFixture[str]) -> None:
        write_block_response("test reason")
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["decision"] == "block"
        assert data["reason"] == "test reason"


class TestGetWorkingDirectory:
    def test_uses_cwd_from_hook_input(self) -> None:
        result = get_working_directory({"cwd": "/tmp/test"})
        assert result == "/tmp/test"

    def test_uses_env_when_no_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/env/dir")
        result = get_working_directory({})
        assert result == "/env/dir"

    def test_falls_back_to_os_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = get_working_directory({})
        assert result  # Should be a non-empty string

    def test_strips_whitespace_from_cwd(self) -> None:
        result = get_working_directory({"cwd": "  /tmp/test  "})
        assert result == "/tmp/test"

    def test_ignores_empty_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/fallback")
        result = get_working_directory({"cwd": "   "})
        assert result == "/fallback"


class TestMainAllowPath:
    @patch("invoke_branch_protection_guard.sys.stdin", new_callable=StringIO)
    def test_allows_when_stdin_empty(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_branch_protection_guard.sys.stdin")
    def test_allows_when_stdin_is_tty(self, mock_stdin: MagicMock) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_branch_protection_guard.subprocess.run")
    @patch("invoke_branch_protection_guard.sys.stdin", new_callable=StringIO)
    def test_allows_on_feature_branch(
        self,
        mock_stdin: StringIO,
        mock_run: MagicMock,
    ) -> None:
        mock_stdin.write("{}")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="feat/my-feature\n",
                stderr="",
            )
            assert main() == 0

    @patch("invoke_branch_protection_guard.sys.stdin", new_callable=StringIO)
    def test_allows_on_invalid_json(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("not json")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainBlockPath:
    @patch("invoke_branch_protection_guard.subprocess.run")
    @patch("invoke_branch_protection_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_on_main_branch(
        self,
        mock_stdin: StringIO,
        mock_run: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_stdin.write("{}")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="main\n",
                stderr="",
            )
            assert main() == 2
            captured = capsys.readouterr()
            data = json.loads(captured.out.strip())
            assert data["decision"] == "block"
            assert "main" in data["reason"]

    @patch("invoke_branch_protection_guard.subprocess.run")
    @patch("invoke_branch_protection_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_on_master_branch(
        self,
        mock_stdin: StringIO,
        mock_run: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        mock_stdin.write("{}")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="master\n",
                stderr="",
            )
            assert main() == 2

    @patch("invoke_branch_protection_guard.subprocess.run")
    @patch("invoke_branch_protection_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_when_not_git_repo(
        self,
        mock_stdin: StringIO,
        mock_run: MagicMock,
    ) -> None:
        mock_stdin.write("{}")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository",
            )
            assert main() == 2

    @patch("invoke_branch_protection_guard.subprocess.run")
    @patch("invoke_branch_protection_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_when_git_fails(
        self,
        mock_stdin: StringIO,
        mock_run: MagicMock,
    ) -> None:
        mock_stdin.write("{}")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error occurred",
            )
            assert main() == 2

    @patch("invoke_branch_protection_guard.subprocess.run")
    @patch("invoke_branch_protection_guard.sys.stdin", new_callable=StringIO)
    def test_blocks_on_subprocess_exception(
        self,
        mock_stdin: StringIO,
        mock_run: MagicMock,
    ) -> None:
        mock_stdin.write("{}")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            mock_run.side_effect = OSError("git not found")
            assert main() == 2


class TestProtectedBranches:
    def test_main_is_protected(self) -> None:
        assert "main" in PROTECTED_BRANCHES

    def test_master_is_protected(self) -> None:
        assert "master" in PROTECTED_BRANCHES
