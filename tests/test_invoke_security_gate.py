"""Tests for invoke_security_gate.py PreToolUse hook."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root / ".claude" / "hooks" / "PreToolUse"))

from invoke_security_gate import (  # noqa: E402
    find_security_evidence,
    is_auth_path,
    main,
)


class TestIsAuthPath:
    @pytest.mark.parametrize(
        "path",
        [
            "src/Auth/LoginController.cs",
            "src/auth/handler.py",
            "lib/Authentication/oauth.ts",
            "lib/authorization/rbac.py",
            "app/middleware/authMiddleware.js",
            "config.auth.ts",
            "server.auth.py",
            "services/auth/tokens.go",
            "/home/user/project/Auth/models.cs",
            "Auth/Login.cs",
            "auth/handler.py",
            "Authentication/oauth.ts",
            "authorization/rbac.py",
            "middleware/authHandler.js",
            "app/Middleware/auth.js",
        ],
    )
    def test_matches_auth_paths(self, path: str) -> None:
        assert is_auth_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/controllers/UserController.cs",
            "lib/utils/helpers.py",
            "README.md",
            "src/author/book.py",
            "docs/authentication-guide.md",
            "",
        ],
    )
    def test_rejects_non_auth_paths(self, path: str) -> None:
        assert is_auth_path(path) is False


class TestFindSecurityEvidence:
    def test_finds_security_report(self, tmp_path: Path) -> None:
        security_dir = tmp_path / ".agents" / "security"
        security_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (security_dir / f"{today}-security-review.md").write_text("review")

        assert find_security_evidence(str(tmp_path)) is True

    def test_finds_session_log_evidence(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log = sessions_dir / f"{today}-session-01.json"
        log.write_text(json.dumps({"notes": "security agent reviewed auth changes"}))

        assert find_security_evidence(str(tmp_path)) is True

    def test_no_evidence_returns_false(self, tmp_path: Path) -> None:
        assert find_security_evidence(str(tmp_path)) is False

    def test_no_evidence_with_empty_dirs(self, tmp_path: Path) -> None:
        (tmp_path / ".agents" / "security").mkdir(parents=True)
        (tmp_path / ".agents" / "sessions").mkdir(parents=True)
        assert find_security_evidence(str(tmp_path)) is False

    def test_old_security_report_not_found(self, tmp_path: Path) -> None:
        security_dir = tmp_path / ".agents" / "security"
        security_dir.mkdir(parents=True)
        (security_dir / "2020-01-01-security-review.md").write_text("old")
        assert find_security_evidence(str(tmp_path)) is False

    def test_session_log_without_security_markers(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log = sessions_dir / f"{today}-session-01.json"
        log.write_text(json.dumps({"notes": "implemented feature"}))

        assert find_security_evidence(str(tmp_path)) is False


class TestMainAllowPath:
    @patch("invoke_security_gate.sys.stdin")
    def test_allows_when_stdin_is_tty(self, mock_stdin: MagicMock) -> None:
        mock_stdin.isatty.return_value = True
        assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_when_stdin_empty(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_non_auth_file(self, mock_stdin: StringIO) -> None:
        hook_input = {"tool_input": {"file_path": "src/utils/helpers.py"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_missing_file_path(self, mock_stdin: StringIO) -> None:
        hook_input = {"tool_input": {"command": "echo hello"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.find_security_evidence", return_value=True)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_auth_file_with_evidence(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
    ) -> None:
        hook_input = {"tool_input": {"file_path": "src/Auth/Login.cs"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_allows_invalid_tool_input(self, mock_stdin: StringIO) -> None:
        hook_input = {"tool_input": "not a dict"}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0


class TestMainBlockPath:
    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_auth_file_without_evidence(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        hook_input = {"tool_input": {"file_path": "src/Auth/Login.cs"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        captured = capsys.readouterr()
        assert "Security Review Required" in captured.out
        assert "src/Auth/Login.cs" in captured.out
        assert "Blocked" in captured.err

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_middleware_auth_file(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        hook_input = {"tool_input": {"file_path": "app/middleware/authHandler.js"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        captured = capsys.readouterr()
        assert "Security Review Required" in captured.out

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_blocks_auth_extension_file(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
        _mock_evidence: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        hook_input = {"tool_input": {"file_path": "server.auth.ts"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 2
        captured = capsys.readouterr()
        assert "Security Review Required" in captured.out


class TestMainFailOpen:
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_fail_open_on_json_error(self, mock_stdin: StringIO) -> None:
        mock_stdin.write("not json")
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0

    @patch("invoke_security_gate.get_project_directory", side_effect=RuntimeError("boom"))
    @patch("invoke_security_gate.sys.stdin", new_callable=StringIO)
    def test_fail_open_on_project_dir_error(
        self,
        mock_stdin: StringIO,
        _mock_project: MagicMock,
    ) -> None:
        hook_input = {"tool_input": {"file_path": "src/Auth/Login.cs"}}
        mock_stdin.write(json.dumps(hook_input))
        mock_stdin.seek(0)
        with patch.object(mock_stdin, "isatty", return_value=False):
            assert main() == 0
