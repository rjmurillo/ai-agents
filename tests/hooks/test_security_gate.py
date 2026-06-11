#!/usr/bin/env python3
"""Tests for the invoke_security_gate PreToolUse hook.

Covers: auth file detection, security evidence checking, blocking behavior,
exit codes (0=allow, 2=block), fail-closed on errors.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

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
        assert not invoke_security_gate.is_auth_path("")


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

    def test_exits_2_on_invalid_json(self, mock_stdin: Callable[[str], None], capsys):
        mock_stdin("not json")
        result = invoke_security_gate.main()
        assert result == 2
        assert "Security Gate Error" in capsys.readouterr().out

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

    def test_exits_2_for_empty_file_path(
        self, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(
            json.dumps(
                {"tool_name": "Edit", "tool_input": {"file_path": ""}}
            )
        )
        result = invoke_security_gate.main()
        assert result == 2
        assert "file_path" in capsys.readouterr().out

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

    def test_exits_2_for_non_dict_tool_input(
        self, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(json.dumps({"tool_name": "Edit", "tool_input": "string"}))
        result = invoke_security_gate.main()
        assert result == 2
        assert "tool_input" in capsys.readouterr().out

    def test_fails_closed_on_exception(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/project/Auth/handler.py"},
                }
            )
        )
        with patch(
            "invoke_security_gate.find_security_evidence",
            side_effect=RuntimeError("evidence scan failed"),
        ), patch("invoke_security_gate.get_project_directory", return_value="/project"):
            result = invoke_security_gate.main()
        assert result == 2


# ---------------------------------------------------------------------------
# Streaming read tests for find_security_evidence
# ---------------------------------------------------------------------------


class TestFindSecurityEvidenceStreaming:
    """Verify find_security_evidence streams line-by-line."""

    def _make_large_log(self, sessions_dir: Path, today: str, *, pattern_at_start: bool) -> Path:
        """Create a large fake session log."""
        log = sessions_dir / f"{today}-session-001.json"
        trigger_line = '  "notes": "security review completed"\n'
        filler_line = '  "data": "' + "x" * 1000 + '",\n'
        # 2,000 x ~1KB lines (~2MB) written incrementally: large enough to
        # exercise streaming, without building a multi-MB string in memory
        # or slowing CI (a prior 50,000-line join allocated ~50MB).
        with log.open("w", encoding="utf-8") as handle:
            if pattern_at_start:
                handle.write(trigger_line)
            for _ in range(2000):
                handle.write(filler_line)
        return log

    def test_large_log_with_pattern_at_line1_returns_true(self, tmp_path: Path) -> None:
        """Pattern at first line of a large file is found."""
        from datetime import UTC, datetime

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        self._make_large_log(sessions_dir, today, pattern_at_start=True)
        assert invoke_security_gate.find_security_evidence(str(tmp_path))

    def test_large_log_without_pattern_returns_false(self, tmp_path: Path) -> None:
        """Large file with no pattern returns False."""
        from datetime import UTC, datetime

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        self._make_large_log(sessions_dir, today, pattern_at_start=False)
        assert not invoke_security_gate.find_security_evidence(str(tmp_path))

    def test_unreadable_log_does_not_mask_later_evidence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One unreadable log cannot hide evidence in a later log."""
        from datetime import UTC, datetime

        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        unreadable = sessions_dir / f"{today}-session-001.json"
        unreadable.write_text("unreadable", encoding="utf-8")
        readable = sessions_dir / f"{today}-session-002.json"
        readable.write_text("security review completed", encoding="utf-8")

        original_open = Path.open

        def fake_open(path: Path, *args, **kwargs):
            if path == unreadable:
                raise OSError("permission denied")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", fake_open)
        assert invoke_security_gate.find_security_evidence(str(tmp_path))
