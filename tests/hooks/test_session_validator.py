"""Tests for Stop invoke_session_validator hook.

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

from invoke_session_validator import (  # noqa: E402
    PLACEHOLDER_PATTERNS,
    REQUIRED_JSON_KEYS,
    get_incomplete_session_end_items,
    get_missing_keys,
    get_project_directory,
    get_today_session_logs,
    is_session_end_missing,
    log_session_end_skip,
    main,
    write_continue_response,
)


class TestGetProjectDirectory:
    """Tests for project directory resolution."""

    def test_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/project")
        assert get_project_directory({"cwd": "/other"}) == "/project"

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


class TestGetTodaySessionLogs:
    """Tests for session log discovery."""

    def test_directory_missing(self, tmp_path: Path) -> None:
        result = get_today_session_logs(str(tmp_path / "nonexistent"))
        assert isinstance(result, dict)
        assert result.get("directory_missing") is True

    def test_log_missing(self, tmp_path: Path) -> None:
        result = get_today_session_logs(str(tmp_path))
        assert isinstance(result, dict)
        assert result.get("log_missing") is True

    def test_finds_log(self, tmp_path: Path) -> None:
        log = tmp_path / "2026-03-01-session-01.json"
        log.write_text('{"test": true}')

        with patch("invoke_session_validator.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-03-01"
            result = get_today_session_logs(str(tmp_path))

        assert isinstance(result, Path)
        assert "session-01" in result.name

    def test_returns_most_recent(self, tmp_path: Path) -> None:
        log1 = tmp_path / "2026-03-01-session-01.json"
        log1.write_text("session 1")
        log2 = tmp_path / "2026-03-01-session-02.json"
        log2.write_text("session 2")
        log2.touch()

        with patch("invoke_session_validator.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = "2026-03-01"
            result = get_today_session_logs(str(tmp_path))

        assert isinstance(result, Path)
        assert "session-02" in result.name


class TestGetMissingKeys:
    """Tests for JSON key validation."""

    def test_all_keys_present(self) -> None:
        content = json.dumps({
            "session": {"id": "test"},
            "protocolCompliance": {"test": True},
            "work": {"items": ["task1"]},
            "outcomes": {"result": "completed"},
        })
        assert get_missing_keys(content) == []

    def test_all_keys_missing(self) -> None:
        content = json.dumps({"unrelated": "data"})
        missing = get_missing_keys(content)
        assert len(missing) >= len(REQUIRED_JSON_KEYS)

    def test_some_keys_missing(self) -> None:
        content = json.dumps({
            "session": {"id": "test"},
            "work": {"items": ["task1"]},
        })
        missing = get_missing_keys(content)
        assert "protocolCompliance" in missing
        assert "outcomes" in missing

    def test_outcomes_with_placeholder_tbd(self) -> None:
        content = json.dumps({
            "session": {"id": "test"},
            "protocolCompliance": {"test": True},
            "work": {"items": ["task1"]},
            "outcomes": {"result": "TBD"},
        })
        missing = get_missing_keys(content)
        assert any("placeholder" in m for m in missing)

    def test_outcomes_with_placeholder_todo(self) -> None:
        content = json.dumps({
            "session": {"id": "test"},
            "protocolCompliance": {"test": True},
            "work": {"items": ["task1"]},
            "outcomes": {"result": "TODO"},
        })
        missing = get_missing_keys(content)
        assert any("placeholder" in m for m in missing)

    def test_invalid_json(self) -> None:
        missing = get_missing_keys("not valid json")
        assert len(missing) > 0
        assert any("JSON" in m for m in missing)


class TestRequiredJsonKeys:
    """Tests for key constants."""

    def test_keys_not_empty(self) -> None:
        assert len(REQUIRED_JSON_KEYS) >= 4


class TestPlaceholderPatterns:
    """Tests for placeholder pattern constants."""

    def test_patterns_not_empty(self) -> None:
        assert len(PLACEHOLDER_PATTERNS) > 0

    def test_all_patterns_valid_regex(self) -> None:
        import re
        for pattern in PLACEHOLDER_PATTERNS:
            assert isinstance(pattern, re.Pattern)


@pytest.fixture(autouse=True)
def _no_consumer_repo_skip():
    with patch("invoke_session_validator.skip_if_consumer_repo", return_value=False):
        yield


class TestMainAllow:
    """Tests for main() allowing stop."""

    def test_tty_stdin(self) -> None:
        with patch("invoke_session_validator.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            assert main() == 0

    def test_empty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert main() == 0

    def test_directory_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "nonexistent"))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))
        assert main() == 0

    def test_complete_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        content = json.dumps({
            "session": {"id": "test", "date": "2026-03-01"},
            "protocolCompliance": {
                "sessionStart": {"complete": True},
                "sessionEnd": {
                    "changesCommitted": {"level": "MUST", "Complete": True},
                    "lintRun": {"level": "MUST", "Complete": True},
                    "checklistComplete": {"level": "MUST", "Complete": True},
                },
            },
            "work": {"items": ["implemented feature X"]},
            "outcomes": {"result": "All tests passing, feature deployed"},
        })

        log = sessions_dir / "2026-03-01-session-01.json"
        log.write_text(content)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("invoke_session_validator.get_today_session_logs", return_value=log):
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
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch(
            "invoke_session_validator.get_today_session_logs",
            return_value={"log_missing": True, "today": "2026-03-01"},
        ):
            assert main() == 0

        captured = capsys.readouterr()
        resp = json.loads(captured.out.strip())
        assert resp["continue"] is True
        assert "Session log missing" in resp["reason"]

    def test_incomplete_log(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture
    ) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-03-01-session-01.json"
        log.write_text(json.dumps({"session": {"id": "test"}}))

        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("invoke_session_validator.get_today_session_logs", return_value=log):
            assert main() == 0

        captured = capsys.readouterr()
        resp = json.loads(captured.out.strip())
        assert resp["continue"] is True
        assert "Session log incomplete" in resp["reason"]

    def test_file_error_produces_continue(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture
    ) -> None:
        """OS errors should produce continue response, not crash."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        data = json.dumps({"cwd": str(tmp_path)})
        monkeypatch.setattr("sys.stdin", io.StringIO(data))

        with patch("invoke_session_validator.get_today_session_logs") as mock_find:
            mock_find.side_effect = OSError("disk error")
            assert main() == 0

        captured = capsys.readouterr()
        resp = json.loads(captured.out.strip())
        assert resp["continue"] is True


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_session_validator_as_script(self) -> None:
        import subprocess

        hook_path = str(HOOK_DIR / "invoke_session_validator.py")
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

        hook_path = str(HOOK_DIR / "invoke_session_validator.py")
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0


class TestSessionEndCompliance:
    """Tests for session-end checklist enforcement in the Stop hook."""

    def test_is_session_end_missing_when_absent(self) -> None:
        data = {"protocolCompliance": {"sessionStart": {}}}
        assert is_session_end_missing(data) is True

    def test_is_session_end_missing_when_present(self) -> None:
        data = {"protocolCompliance": {"sessionEnd": {"item": {"level": "MUST", "Complete": True}}}}
        assert is_session_end_missing(data) is False

    def test_is_session_end_missing_no_protocol(self) -> None:
        data = {"session": {}}
        assert is_session_end_missing(data) is True

    def test_incomplete_items_returns_must_incomplete(self) -> None:
        data = {
            "protocolCompliance": {
                "sessionEnd": {
                    "changesCommitted": {"level": "MUST", "Complete": False},
                    "lintRun": {"level": "MUST", "Complete": True},
                    "optional": {"level": "SHOULD", "Complete": False},
                }
            }
        }
        result = get_incomplete_session_end_items(data)
        assert result == ["changesCommitted"]

    def test_incomplete_items_all_complete(self) -> None:
        data = {
            "protocolCompliance": {
                "sessionEnd": {
                    "changesCommitted": {"level": "MUST", "Complete": True},
                    "lintRun": {"level": "MUST", "Complete": True},
                }
            }
        }
        assert get_incomplete_session_end_items(data) == []

    def test_incomplete_items_empty_when_no_session_end(self) -> None:
        data = {"protocolCompliance": {}}
        assert get_incomplete_session_end_items(data) == []

    def test_log_session_end_skip_writes_jsonl(self, tmp_path: Path) -> None:
        sessions_dir = str(tmp_path / "sessions")
        log_session_end_skip("S-1", "2026-01-01-session-01.json", sessions_dir)
        skip_file = tmp_path / "sessions" / "session-end-skips.jsonl"
        assert skip_file.exists()
        record = json.loads(skip_file.read_text().strip())
        assert record["event"] == "session_closed_without_session_end"
        assert record["session_id"] == "S-1"
        assert record["session_log"] == "2026-01-01-session-01.json"

    def test_log_session_end_skip_nonblocking_on_error(self) -> None:
        """Skip logging should not raise even if path is invalid."""
        # /dev/null/impossible is not writable - should silently fail
        log_session_end_skip("S-1", "log.json", "/dev/null/impossible")
