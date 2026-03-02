"""Tests for Stop session_validator hook.

Verifies that session log completeness is validated before Claude stops,
and missing/incomplete sections trigger continue responses.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "Stop"
sys.path.insert(0, str(HOOK_DIR))

from session_validator import (
    PLACEHOLDER_PATTERNS,
    REQUIRED_SECTIONS,
    find_today_session_log,
    get_missing_sections,
    get_project_directory,
    main,
    write_continue_response,
)


class TestGetProjectDirectory:
    """Tests for project directory resolution."""

    def test_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/project")
        assert get_project_directory({}) == "/project"

    def test_cwd_from_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        assert get_project_directory({"cwd": "/from/input"}) == "/from/input"

    def test_fallback_to_os_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        result = get_project_directory({})
        assert os.path.isabs(result)


class TestWriteContinueResponse:
    """Tests for continue response output."""

    def test_outputs_json(self, capsys: pytest.CaptureFixture) -> None:
        write_continue_response("test reason")
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["continue"] is True
        assert data["reason"] == "test reason"


class TestFindTodaySessionLog:
    """Tests for session log discovery."""

    def test_directory_missing(self, tmp_path: Path) -> None:
        result = find_today_session_log(str(tmp_path / "nonexistent"))
        assert result["directory_missing"] is True

    def test_log_missing(self, tmp_path: Path) -> None:
        with patch("session_validator.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            result = find_today_session_log(str(tmp_path))
        assert result["log_missing"] is True
        assert result["today"] == "2026-03-01"

    def test_finds_log(self, tmp_path: Path) -> None:
        log = tmp_path / "2026-03-01-session-01.md"
        log.write_text("# Session Log")

        with patch("session_validator.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            result = find_today_session_log(str(tmp_path))

        assert "path" in result
        assert result["name"] == "2026-03-01-session-01.md"

    def test_returns_most_recent(self, tmp_path: Path) -> None:
        log1 = tmp_path / "2026-03-01-session-01.md"
        log1.write_text("session 1")
        log2 = tmp_path / "2026-03-01-session-02.md"
        log2.write_text("session 2")
        log2.touch()

        with patch("session_validator.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            result = find_today_session_log(str(tmp_path))

        assert "session-02" in result["name"]


class TestGetMissingSections:
    """Tests for section validation."""

    def test_all_sections_present(self) -> None:
        # Build content with all required sections, each with substantial text
        content = ""
        for section in REQUIRED_SECTIONS:
            content += f"{section}\n"
            if section == "## Outcomes":
                content += "Completed the implementation of all features. " * 5 + "\n"
            else:
                content += "Content for this section here.\n"
        assert get_missing_sections(content) == []

    def test_all_sections_missing(self) -> None:
        missing = get_missing_sections("# Empty Log\nNothing here")
        assert len(missing) >= len(REQUIRED_SECTIONS)

    def test_some_sections_missing(self) -> None:
        content = "## Session Context\n## Work Log\n## Outcomes\n" + "x" * 60
        missing = get_missing_sections(content)
        assert "## Implementation Plan" in missing
        assert "## Decisions" in missing
        assert "## Session Context" not in missing

    def test_outcomes_with_placeholder_tbd(self) -> None:
        content = "\n".join(REQUIRED_SECTIONS) + "\n## Outcomes\nTBD\n## Other"
        missing = get_missing_sections(content)
        assert any("Outcomes" in m and "incomplete" in m for m in missing)

    def test_outcomes_with_placeholder_todo(self) -> None:
        content = "\n".join(REQUIRED_SECTIONS) + "\n## Outcomes\nTODO\n## Other"
        missing = get_missing_sections(content)
        assert any("Outcomes" in m and "incomplete" in m for m in missing)

    def test_outcomes_too_short(self) -> None:
        content = "\n".join(REQUIRED_SECTIONS) + "\n## Outcomes\nShort."
        missing = get_missing_sections(content)
        assert any("Outcomes" in m and "incomplete" in m for m in missing)

    def test_outcomes_with_pending(self) -> None:
        content = "\n".join(REQUIRED_SECTIONS) + "\n## Outcomes\n(pending)\n## Other"
        missing = get_missing_sections(content)
        assert any("Outcomes" in m for m in missing)

    def test_outcomes_sufficient(self) -> None:
        outcomes = "Completed implementation of feature X with tests. " * 3
        # Build content with all sections, giving Outcomes substantial text
        content = ""
        for section in REQUIRED_SECTIONS:
            content += f"{section}\n"
            if section == "## Outcomes":
                content += outcomes + "\n"
            else:
                content += "Content here.\n"
        missing = get_missing_sections(content)
        # Should not have outcomes incomplete flag
        assert not any("incomplete" in m for m in missing)


class TestRequiredSections:
    """Tests for section constants."""

    def test_sections_not_empty(self) -> None:
        assert len(REQUIRED_SECTIONS) >= 5

    def test_all_start_with_heading(self) -> None:
        for section in REQUIRED_SECTIONS:
            assert section.startswith("## ")


class TestPlaceholderPatterns:
    """Tests for placeholder pattern constants."""

    def test_patterns_not_empty(self) -> None:
        assert len(PLACEHOLDER_PATTERNS) > 0

    def test_all_patterns_valid_regex(self) -> None:
        import re
        for pattern in PLACEHOLDER_PATTERNS:
            re.compile(pattern)


class TestMainAllow:
    """Tests for main() allowing stop."""

    def test_tty_stdin(self) -> None:
        with patch("session_validator.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    def test_directory_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "nonexistent"))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_complete_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        outcomes = "Completed feature implementation with full test coverage. " * 3
        # Build content with all sections, giving Outcomes substantial text
        content = ""
        for section in REQUIRED_SECTIONS:
            content += f"{section}\n"
            if section == "## Outcomes":
                content += outcomes + "\n"
            else:
                content += "Content here.\n"

        log = sessions_dir / "2026-03-01-session-01.md"
        log.write_text(content)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("session_validator.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            assert main() == 0

        captured = capsys.readouterr()
        # No continue response should be printed for a complete log
        assert not captured.out.strip()

    def test_invalid_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad"))
        assert main() == 0


class TestMainContinue:
    """Tests for main() requesting continuation."""

    def test_log_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("session_validator.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            assert main() == 0

        captured = capsys.readouterr()
        resp = json.loads(captured.out.strip())
        assert resp["continue"] is True
        assert "Session log missing" in resp["reason"]

    def test_incomplete_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-03-01-session-01.md"
        log.write_text("## Session Context\nSome work")

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("session_validator.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-03-01"
            assert main() == 0

        captured = capsys.readouterr()
        resp = json.loads(captured.out.strip())
        assert resp["continue"] is True
        assert "incomplete" in resp["reason"].lower() or "Missing" in resp["reason"]

    def test_file_error_produces_continue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        """OS errors should produce continue response, not crash."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("session_validator.find_today_session_log") as mock_find:
            mock_find.side_effect = OSError("disk error")
            assert main() == 0

        captured = capsys.readouterr()
        resp = json.loads(captured.out.strip())
        assert resp["continue"] is True


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_session_validator_as_script(self) -> None:
        import subprocess

        hook_path = str(HOOK_DIR / "session_validator.py")
        result = subprocess.run(
            ["python3", hook_path],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(HOOK_DIR / "session_validator.py")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
