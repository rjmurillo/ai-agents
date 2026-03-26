#!/usr/bin/env python3
"""Tests for the invoke_retrospective_gate PreToolUse hook.

Covers: git push detection, retrospective evidence checking, bypass conditions,
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

import invoke_retrospective_gate  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests for is_git_push_command
# ---------------------------------------------------------------------------


class TestIsGitPushCommand:
    def test_detects_simple_push(self):
        assert invoke_retrospective_gate.is_git_push_command("git push")

    def test_detects_push_with_remote(self):
        assert invoke_retrospective_gate.is_git_push_command("git push origin main")

    def test_rejects_non_push(self):
        assert not invoke_retrospective_gate.is_git_push_command("git commit -m test")

    def test_rejects_none(self):
        assert not invoke_retrospective_gate.is_git_push_command(None)

    def test_rejects_empty(self):
        assert not invoke_retrospective_gate.is_git_push_command("")


# ---------------------------------------------------------------------------
# Unit tests for check_retrospective_in_session_log
# ---------------------------------------------------------------------------


class TestCheckRetrospectiveInSessionLog:
    def test_finds_retrospective_section(self, tmp_path):
        log = tmp_path / "session.json"
        log.write_text('{"notes": "## Retrospective\\nLearnings captured"}')
        assert invoke_retrospective_gate.check_retrospective_in_session_log(log)

    def test_finds_retro_file_reference(self, tmp_path):
        log = tmp_path / "session.json"
        log.write_text('{"notes": "See .agents/retrospective/ for details"}')
        assert invoke_retrospective_gate.check_retrospective_in_session_log(log)

    def test_returns_false_when_no_evidence(self, tmp_path):
        log = tmp_path / "session.json"
        log.write_text('{"notes": "Just normal session work"}')
        assert not invoke_retrospective_gate.check_retrospective_in_session_log(log)


# ---------------------------------------------------------------------------
# Unit tests for check_retrospective_file_exists
# ---------------------------------------------------------------------------


class TestCheckRetrospectiveFileExists:
    @patch("invoke_retrospective_gate.datetime")
    def test_finds_today_retro_file(self, mock_dt, tmp_path):
        mock_dt.now.return_value.strftime.return_value = "2026-03-26"
        retro_dir = tmp_path / ".agents" / "retrospective"
        retro_dir.mkdir(parents=True)
        (retro_dir / "2026-03-26-session-retro.md").write_text("learnings")
        assert invoke_retrospective_gate.check_retrospective_file_exists(
            str(tmp_path)
        )

    @patch("invoke_retrospective_gate.datetime")
    def test_returns_false_when_no_retro_dir(self, mock_dt, tmp_path):
        mock_dt.now.return_value.strftime.return_value = "2026-03-26"
        assert not invoke_retrospective_gate.check_retrospective_file_exists(
            str(tmp_path)
        )


# ---------------------------------------------------------------------------
# Unit tests for main
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_0_on_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        result = invoke_retrospective_gate.main()
        assert result == 0

    def test_exits_0_on_empty_input(self, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        result = invoke_retrospective_gate.main()
        assert result == 0

    def test_exits_0_on_invalid_json(self, mock_stdin: Callable[[str], None]):
        mock_stdin("not json")
        result = invoke_retrospective_gate.main()
        assert result == 0

    def test_exits_0_for_non_push(self, mock_stdin: Callable[[str], None]):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git commit -m test"}})
        )
        result = invoke_retrospective_gate.main()
        assert result == 0

    def test_exits_0_for_missing_command(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_input": {}}))
        result = invoke_retrospective_gate.main()
        assert result == 0

    @patch("invoke_retrospective_gate.get_project_directory", return_value="/project")
    @patch("os.path.isdir", return_value=False)
    def test_exits_0_when_no_sessions_dir(
        self, _isdir, _dir, mock_stdin: Callable[[str], None]
    ):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git push origin main"}})
        )
        result = invoke_retrospective_gate.main()
        assert result == 0

    @patch("invoke_retrospective_gate.check_retrospective_file_exists", return_value=True)
    @patch("invoke_retrospective_gate.check_documentation_only", return_value=False)
    @patch("invoke_retrospective_gate.check_trivial_session", return_value=False)
    @patch("invoke_retrospective_gate.get_today_session_log", return_value=None)
    @patch("invoke_retrospective_gate.get_project_directory", return_value="/project")
    @patch("os.path.isdir", return_value=True)
    @patch("os.environ.get", return_value=None)
    def test_exits_0_when_retro_file_exists(
        self,
        _env,
        _isdir,
        _dir,
        _log,
        _trivial,
        _doc,
        _retro,
        mock_stdin: Callable[[str], None],
    ):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git push"}})
        )
        result = invoke_retrospective_gate.main()
        assert result == 0

    def test_exits_0_with_env_bypass(
        self, mock_stdin: Callable[[str], None], monkeypatch
    ):
        monkeypatch.setenv("SKIP_RETROSPECTIVE_GATE", "true")
        mock_stdin(
            json.dumps({"tool_input": {"command": "git push"}})
        )
        with patch(
            "invoke_retrospective_gate.get_project_directory",
            return_value="/project",
        ), patch("os.path.isdir", return_value=True):
            result = invoke_retrospective_gate.main()
        assert result == 0

    @patch(
        "invoke_retrospective_gate.check_retrospective_file_exists",
        return_value=False,
    )
    @patch("invoke_retrospective_gate.check_documentation_only", return_value=False)
    @patch("invoke_retrospective_gate.check_trivial_session", return_value=False)
    @patch("invoke_retrospective_gate.get_today_session_log", return_value=None)
    @patch(
        "invoke_retrospective_gate.get_project_directory", return_value="/project"
    )
    @patch("os.path.isdir", return_value=True)
    @patch("os.environ.get", return_value=None)
    def test_exits_2_when_no_retrospective_evidence(
        self,
        _env,
        _isdir,
        _dir,
        _log,
        _trivial,
        _doc,
        _retro,
        mock_stdin: Callable[[str], None],
        capsys,
    ):
        mock_stdin(
            json.dumps({"tool_input": {"command": "git push origin main"}})
        )
        result = invoke_retrospective_gate.main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out

    def test_fails_open_on_exception(self, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_input": None}))
        result = invoke_retrospective_gate.main()
        assert result == 0
