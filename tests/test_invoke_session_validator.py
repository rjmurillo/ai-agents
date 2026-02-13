#!/usr/bin/env python3
"""Tests for Stop/invoke_session_validator.py."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook directory to path for import
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "Stop"),
)

import invoke_session_validator as hook


class TestGetMissingSections:
    """Tests for get_missing_sections()."""

    def test_all_sections_present(self) -> None:
        content = (
            "## Session Context\nSome context\n"
            "## Implementation Plan\nThe plan\n"
            "## Work Log\nWork done\n"
            "## Decisions\nDecisions made\n"
            "## Outcomes\nThis is a detailed outcome section with enough content "
            "to exceed the 50 character threshold.\n"
            "## Files Changed\nfiles\n"
            "## Follow-up Actions\nactions\n"
        )
        assert hook.get_missing_sections(content) == []

    def test_detects_missing_section(self) -> None:
        content = "## Session Context\nSome context\n## Work Log\nWork done\n"
        missing = hook.get_missing_sections(content)
        assert "## Implementation Plan" in missing
        assert "## Decisions" in missing

    def test_detects_placeholder_in_outcomes(self) -> None:
        content = (
            "## Session Context\nSome context\n"
            "## Implementation Plan\nplan\n"
            "## Work Log\nWork done\n"
            "## Decisions\ndecisions\n"
            "## Outcomes\nTBD\n"
            "## Files Changed\nfiles\n"
            "## Follow-up Actions\nactions\n"
        )
        missing = hook.get_missing_sections(content)
        assert any("Outcomes" in s and "incomplete" in s for s in missing)

    def test_detects_todo_placeholder(self) -> None:
        content = "## Outcomes\nTODO: fill this in later\n"
        missing = hook.get_missing_sections(content)
        assert any("Outcomes" in s and "incomplete" in s for s in missing)

    def test_detects_short_outcomes(self) -> None:
        content = "## Outcomes\nDone.\n"
        missing = hook.get_missing_sections(content)
        assert any("Outcomes" in s and "incomplete" in s for s in missing)

    def test_detects_pending_placeholder(self) -> None:
        content = "## Outcomes\n(pending)\n"
        missing = hook.get_missing_sections(content)
        assert any("Outcomes" in s and "incomplete" in s for s in missing)


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
        log1 = tmp_path / f"{today}-session-01.md"
        log2 = tmp_path / f"{today}-session-02.md"
        log1.write_text("first", encoding="utf-8")
        log2.write_text("second", encoding="utf-8")

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
        with patch("sys.stdin", new_callable=lambda: io.StringIO):
            # StringIO has no isatty, mock it
            mock_stdin = io.StringIO("")
            mock_stdin.isatty = lambda: True  # type: ignore[attr-defined,method-assign]
            with patch("sys.stdin", mock_stdin):
                assert hook.main() == 0

    def test_exits_zero_on_empty_input(self) -> None:
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]
        with patch("sys.stdin", mock_stdin):
            assert hook.main() == 0

    def test_outputs_continue_on_missing_log(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        input_data = json.dumps({"cwd": str(tmp_path)})
        mock_stdin = io.StringIO(input_data)
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]

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
        log = sessions_dir / f"{today}-session-01.md"
        log.write_text("## Session Context\nSome context\n", encoding="utf-8")

        input_data = json.dumps({"cwd": str(tmp_path)})
        mock_stdin = io.StringIO(input_data)
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]

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
        assert "incomplete" in output["reason"]

    def test_silent_exit_when_no_sessions_dir(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        input_data = json.dumps({"cwd": str(tmp_path)})
        mock_stdin = io.StringIO(input_data)
        mock_stdin.isatty = lambda: False  # type: ignore[attr-defined,method-assign]

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
