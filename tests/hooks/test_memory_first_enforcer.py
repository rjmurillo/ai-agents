"""Tests for invoke_memory_first_enforcer.py Claude Code SessionStart hook."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hooks directory to path for import
HOOKS_DIR = (
    Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "SessionStart"
)
sys.path.insert(0, str(HOOKS_DIR))

import invoke_memory_first_enforcer  # noqa: E402


class TestTestMemoryEvidence:
    """Tests for test_memory_evidence."""

    def test_complete_evidence(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text(json.dumps({
            "protocolCompliance": {
                "sessionStart": {
                    "serenaActivated": {"complete": True},
                    "handoffRead": {"complete": True},
                    "memoriesLoaded": {
                        "complete": True,
                        "Evidence": "memory-index, code-style",
                    },
                }
            }
        }))
        result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is True
        assert "memory-index" in result["evidence"]

    def test_missing_protocol_compliance(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text(json.dumps({"notes": "stuff"}))
        result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "Missing" in result["reason"]

    def test_serena_not_activated(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text(json.dumps({
            "protocolCompliance": {
                "sessionStart": {
                    "serenaActivated": {"complete": False},
                    "handoffRead": {"complete": True},
                    "memoriesLoaded": {
                        "complete": True,
                        "Evidence": "stuff",
                    },
                }
            }
        }))
        result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "Serena" in result["reason"]

    def test_handoff_not_read(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text(json.dumps({
            "protocolCompliance": {
                "sessionStart": {
                    "serenaActivated": {"complete": True},
                    "handoffRead": {"complete": False},
                    "memoriesLoaded": {
                        "complete": True,
                        "Evidence": "stuff",
                    },
                }
            }
        }))
        result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "HANDOFF" in result["reason"]

    def test_memories_not_loaded(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text(json.dumps({
            "protocolCompliance": {
                "sessionStart": {
                    "serenaActivated": {"complete": True},
                    "handoffRead": {"complete": True},
                    "memoriesLoaded": {"complete": False},
                }
            }
        }))
        result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "Memories not loaded" in result["reason"]

    def test_empty_evidence(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text(json.dumps({
            "protocolCompliance": {
                "sessionStart": {
                    "serenaActivated": {"complete": True},
                    "handoffRead": {"complete": True},
                    "memoriesLoaded": {
                        "complete": True,
                        "Evidence": "",
                    },
                }
            }
        }))
        result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "empty" in result["reason"]

    def test_invalid_json(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("not valid json {{{")
        result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "invalid JSON" in result["reason"]

    def test_permission_error(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("{}")
        os.chmod(session_log, 0o000)
        try:
            result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
            assert result["complete"] is False
        finally:
            os.chmod(session_log, 0o644)

    def test_file_not_found(self, tmp_path):
        result = invoke_memory_first_enforcer.test_memory_evidence(
            str(tmp_path / "missing.json")
        )
        assert result["complete"] is False
        assert "deleted" in result["reason"]

    def test_missing_serena_key(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text(json.dumps({
            "protocolCompliance": {
                "sessionStart": {
                    "handoffRead": {"complete": True},
                    "memoriesLoaded": {
                        "complete": True,
                        "Evidence": "stuff",
                    },
                }
            }
        }))
        result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is False

    def test_generic_oserror_returns_incomplete(self, tmp_path):
        """Generic OSError hits the catch-all handler."""
        session_log = tmp_path / "session.json"
        session_log.write_text("{}")
        with patch("pathlib.Path.read_text", side_effect=OSError("generic io error")):
            result = invoke_memory_first_enforcer.test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "Error parsing session log" in result["reason"]


class TestInvocationCount:
    """Tests for get_invocation_count and increment_invocation_count."""

    def test_returns_zero_when_no_file(self, tmp_path):
        count = invoke_memory_first_enforcer.get_invocation_count(
            str(tmp_path), "2026-03-01"
        )
        assert count == 0

    def test_increments_count(self, tmp_path):
        state_dir = str(tmp_path / "state")
        count = invoke_memory_first_enforcer.increment_invocation_count(
            state_dir, "2026-03-01"
        )
        assert count == 1
        count = invoke_memory_first_enforcer.increment_invocation_count(
            state_dir, "2026-03-01"
        )
        assert count == 2

    def test_resets_on_new_day(self, tmp_path):
        state_dir = str(tmp_path / "state")
        invoke_memory_first_enforcer.increment_invocation_count(
            state_dir, "2026-03-01"
        )
        invoke_memory_first_enforcer.increment_invocation_count(
            state_dir, "2026-03-01"
        )
        # New day should reset
        count = invoke_memory_first_enforcer.get_invocation_count(
            state_dir, "2026-03-02"
        )
        assert count == 0

    def test_handles_legacy_format(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        state_file = state_dir / "memory-first-counter.txt"
        state_file.write_text("5")
        count = invoke_memory_first_enforcer.get_invocation_count(
            str(state_dir), "2026-03-01"
        )
        assert count == 5

    def test_handles_corrupt_file(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        state_file = state_dir / "memory-first-counter.txt"
        state_file.write_text("not a number")
        count = invoke_memory_first_enforcer.get_invocation_count(
            str(state_dir), "2026-03-01"
        )
        assert count == 0


class TestMain:
    """Tests for main() entry point."""

    @patch("invoke_memory_first_enforcer.skip_if_consumer_repo", return_value=False)
    @patch("invoke_memory_first_enforcer.get_today_session_logs", return_value=[])
    @patch("invoke_memory_first_enforcer.get_project_directory")
    def test_no_session_logs_outputs_guidance(
        self, mock_proj, mock_logs, mock_skip, tmp_path, capsys
    ):
        mock_proj.return_value = str(tmp_path)
        result = invoke_memory_first_enforcer.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR-007" in captured.out

    @patch("invoke_memory_first_enforcer.skip_if_consumer_repo", return_value=False)
    @patch("invoke_memory_first_enforcer.get_project_directory")
    def test_complete_evidence_outputs_verified(
        self, mock_proj, mock_skip, tmp_path, capsys
    ):
        mock_proj.return_value = str(tmp_path)
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log_file = sessions_dir / "2026-03-01-session-01.json"
        log_file.write_text(json.dumps({
            "protocolCompliance": {
                "sessionStart": {
                    "serenaActivated": {"complete": True},
                    "handoffRead": {"complete": True},
                    "memoriesLoaded": {
                        "complete": True,
                        "Evidence": "memory-index",
                    },
                }
            }
        }))
        with patch("invoke_memory_first_enforcer.get_today_session_logs", return_value=[log_file]):
            result = invoke_memory_first_enforcer.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Evidence verified" in captured.out

    @patch("invoke_memory_first_enforcer.skip_if_consumer_repo", return_value=False)
    @patch("invoke_memory_first_enforcer.get_project_directory")
    def test_fails_open_on_exception(self, mock_proj, mock_skip, capsys):
        mock_proj.return_value = "/nonexistent/path"
        with patch.object(
            invoke_memory_first_enforcer, "get_today_session_logs",
            side_effect=Exception("unexpected"),
        ):
            result = invoke_memory_first_enforcer.main()
        assert result == 0


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_memory_first_enforcer_as_script(self):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "SessionStart" / "invoke_memory_first_enforcer.py"
        )
        result = subprocess.run(
            ["python3", hook_path],
            input="",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_main_guard_via_runpy(self, monkeypatch):
        """Cover the sys.exit(main()) line via runpy in-process execution."""
        import runpy

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "SessionStart" / "invoke_memory_first_enforcer.py"
        )
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parents[2]))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
