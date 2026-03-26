#!/usr/bin/env python3
"""Tests for the invoke_security_gate PreToolUse hook.

Covers: auth file detection, security evidence checking, blocking behavior,
exit codes (0=allow, 2=block), fail-open on errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_DIR = str(Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse")
sys.path.insert(0, HOOK_DIR)

import invoke_security_gate  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for is_auth_path
# ---------------------------------------------------------------------------


class TestIsAuthPath:
    def test_matches_auth_directory(self):
        assert invoke_security_gate.is_auth_path("src/Auth/handler.py")

    def test_matches_authentication_directory(self):
        assert invoke_security_gate.is_auth_path("src/Authentication/flow.py")

    def test_matches_authorization_directory(self):
        assert invoke_security_gate.is_auth_path("src/Authorization/policy.py")

    def test_matches_auth_file_extension(self):
        assert invoke_security_gate.is_auth_path("services/user.auth.py")

    def test_matches_middleware_auth(self):
        assert invoke_security_gate.is_auth_path("src/middleware/auth_check.py")

    def test_rejects_non_auth(self):
        assert not invoke_security_gate.is_auth_path("src/utils/helper.py")

    def test_rejects_empty(self):
        assert not invoke_security_gate.is_auth_path("")

    def test_rejects_none_like(self):
        assert not invoke_security_gate.is_auth_path(None)


# ---------------------------------------------------------------------------
# Unit tests for find_security_evidence
# ---------------------------------------------------------------------------


class TestFindSecurityEvidence:
    def test_finds_security_report(self, tmp_path):
        security_dir = tmp_path / ".agents" / "security"
        security_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (security_dir / f"{today}-security-review.md").write_text("reviewed")
        assert invoke_security_gate.find_security_evidence(str(tmp_path))

    def test_finds_session_log_evidence(self, tmp_path):
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log = sessions_dir / f"{today}-session-001.json"
        log.write_text('{"notes": "security review completed with OWASP check"}')
        assert invoke_security_gate.find_security_evidence(str(tmp_path))

    def test_returns_false_when_no_evidence(self, tmp_path):
        assert not invoke_security_gate.find_security_evidence(str(tmp_path))


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        result = invoke_security_gate.main()
        assert result == 0

    def test_exits_0_on_empty_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        result = invoke_security_gate.main()
        assert result == 0

    def test_exits_0_on_invalid_json(self, mock_stdin: Callable[[str], None]):
        mock_stdin("not json")
        result = invoke_security_gate.main()
        assert result == 0

    def test_exits_0_for_non_auth_file(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/project/README.md"},
                }
            )
        )
        result = invoke_security_gate.main()
        assert result == 0

    def test_exits_0_for_empty_file_path(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps(
                {"tool_name": "Edit", "tool_input": {"file_path": ""}}
            )
        )
        result = invoke_security_gate.main()
        assert result == 0

    @patch("invoke_security_gate.find_security_evidence", return_value=True)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    def test_exits_0_when_evidence_exists(
        self,
        _dir,
        _evidence,
        mock_stdin: Callable[[str], None],
    ):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": "/project/Auth/login.py"},
                }
            )
        )
        result = invoke_security_gate.main()
        assert result == 0

    @patch("invoke_security_gate.find_security_evidence", return_value=False)
    @patch("invoke_security_gate.get_project_directory", return_value="/project")
    def test_exits_2_when_no_evidence(
        self,
        _dir,
        _evidence,
        mock_stdin: Callable[[str], None],
        capsys,
    ):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/project/Auth/handler.py"},
                }
            )
        )
        result = invoke_security_gate.main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "Security Review" in captured.out

    def test_exits_0_for_non_dict_tool_input(
        self, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(json.dumps({"tool_name": "Edit", "tool_input": "string"}))
        result = invoke_security_gate.main()
        assert result == 0

    def test_fails_open_on_exception(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Edit", "tool_input": None}))
        result = invoke_security_gate.main()
        assert result == 0
