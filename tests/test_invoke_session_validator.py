#!/usr/bin/env python3
"""Tests for Stop/invoke_session_validator.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add hook directory to path for import
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "Stop"),
)

import invoke_session_validator as hook


class TestGetMissingKeys:
    """Tests for get_missing_keys()."""

    def test_all_keys_present(self) -> None:
        content = json.dumps({
            "session": {"number": 1, "date": "2026-01-01"},
            "protocolCompliance": {"sessionStart": {}},
            "work": {"tasksCompleted": []},
            "outcomes": {"testsRun": "66 passed", "lintClean": True},
        })
        assert hook.get_missing_keys(content) == []

    def test_detects_missing_key(self) -> None:
        content = json.dumps({"session": {"number": 1}})
        missing = hook.get_missing_keys(content)
        assert "protocolCompliance" in missing
        assert "work" in missing
        assert "outcomes" in missing

    def test_detects_empty_key(self) -> None:
        content = json.dumps({
            "session": {},
            "protocolCompliance": {},
            "work": {},
            "outcomes": {},
        })
        missing = hook.get_missing_keys(content)
        assert any("empty" in s for s in missing)

    def test_detects_placeholder_in_outcomes(self) -> None:
        content = json.dumps({
            "session": {"number": 1},
            "protocolCompliance": {"sessionStart": {}},
            "work": {"tasksCompleted": []},
            "outcomes": {"testsRun": "TBD", "lintClean": "pending"},
        })
        missing = hook.get_missing_keys(content)
        assert any("outcomes" in s and "placeholder" in s for s in missing)

    def test_returns_error_for_invalid_json(self) -> None:
        missing = hook.get_missing_keys("not valid json")
        assert any("not valid JSON" in s for s in missing)

    def test_returns_error_for_non_object(self) -> None:
        missing = hook.get_missing_keys(json.dumps([1, 2, 3]))
        assert any("not a JSON object" in s for s in missing)


class TestGetTodaySessionLogs:
    """Tests for get_today_session_logs()."""

    def test_returns_directory_missing_when_not_exists(self) -> None:
        result = hook.get_today_session_logs("/nonexistent/path")
        assert isinstance(result, dict)
        assert result.get("directory_missing") is True

    def test_returns_log_missing_when_no_files(self, tmp_path: Path) -> None:
        result = hook.get_today_session_logs(str(tmp_path))
        assert isinstance(result, dict)
        assert result.get("log_missing") is True

    def test_returns_most_recent_log(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        log1 = tmp_path / f"{today}-session-01.json"
        log2 = tmp_path / f"{today}-session-02.json"
        log1.write_text('{"session":{}}', encoding="utf-8")
        log2.write_text('{"session":{}}', encoding="utf-8")

        result = hook.get_today_session_logs(str(tmp_path))
        assert isinstance(result, Path)
        # Most recent by mtime (both just created, so either is valid)
        assert result.exists()


class TestGetProjectDirectory:
    """Tests for get_project_directory()."""

    def test_uses_env_var(self) -> None:
        with patch.dict("os.environ", {"CLAUDE_PROJECT_DIR": "/my/project"}):
            assert hook.get_project_directory({}) == "/my/project"

    def test_uses_hook_input_cwd(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            import os

            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            result = hook.get_project_directory({"cwd": "/from/hook"})
            assert result == "/from/hook"


class TestMain:
    """Tests for main() entry point."""

    def test_exits_zero_on_tty(self) -> None:
        mock_stdin = MagicMock()
        mock_stdin.read.return_value = ""
        mock_stdin.isatty.return_value = True
        with patch("sys.stdin", mock_stdin):
            assert hook.main() == 0

    def test_exits_zero_on_empty_input(self) -> None:
        mock_stdin = MagicMock()
        mock_stdin.read.return_value = ""
        mock_stdin.isatty.return_value = False
        with patch("sys.stdin", mock_stdin):
            assert hook.main() == 0

    def test_outputs_continue_on_missing_log(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        input_data = json.dumps({"cwd": str(tmp_path)})
        mock_stdin = MagicMock()
        mock_stdin.read.return_value = input_data
        mock_stdin.isatty.return_value = False

        with (
            patch("sys.stdin", mock_stdin),
            patch.dict("os.environ", {}, clear=True),
        ):
            import os

            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["continue"] is True
        assert "Session log missing" in output["reason"]

    def test_outputs_continue_on_incomplete_log(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / f"{today}-session-01.json"
        log.write_text(json.dumps({"session": {"number": 1}}), encoding="utf-8")

        input_data = json.dumps({"cwd": str(tmp_path)})
        mock_stdin = MagicMock()
        mock_stdin.read.return_value = input_data
        mock_stdin.isatty.return_value = False

        with (
            patch("sys.stdin", mock_stdin),
            patch.dict("os.environ", {}, clear=True),
        ):
            import os

            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["continue"] is True
        assert "Missing or incomplete keys" in output["reason"]

    def test_silent_exit_when_no_sessions_dir(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        input_data = json.dumps({"cwd": str(tmp_path)})
        mock_stdin = MagicMock()
        mock_stdin.read.return_value = input_data
        mock_stdin.isatty.return_value = False

        with (
            patch("sys.stdin", mock_stdin),
            patch.dict("os.environ", {}, clear=True),
        ):
            import os

            os.environ.pop("CLAUDE_PROJECT_DIR", None)
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        # No output when directory doesn't exist
        assert captured.out == ""
