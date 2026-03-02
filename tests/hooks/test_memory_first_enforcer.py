"""Tests for memory_first_enforcer.py Claude Code SessionStart hook."""

import datetime
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

import memory_first_enforcer  # noqa: E402


class TestGetProjectDirectory:
    """Tests for _get_project_directory."""

    def test_uses_env_var_when_set(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/custom/path")
        assert memory_first_enforcer._get_project_directory() == "/custom/path"

    def test_walks_up_to_find_git(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        git_dir = tmp_path / "project"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        sub_dir = git_dir / "src" / "deep"
        sub_dir.mkdir(parents=True)
        monkeypatch.chdir(sub_dir)
        result = memory_first_enforcer._get_project_directory()
        assert result == str(git_dir)

    def test_falls_back_to_cwd(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        result = memory_first_enforcer._get_project_directory()
        assert result == str(tmp_path)


class TestGetTodaySessionLogs:
    """Tests for _get_today_session_logs."""

    def test_returns_empty_for_missing_dir(self):
        result = memory_first_enforcer._get_today_session_logs("/nonexistent")
        assert result == []

    def test_returns_matching_logs(self, tmp_path):
        today = datetime.date.today().strftime("%Y-%m-%d")
        (tmp_path / f"{today}-session-01.json").write_text("{}")
        (tmp_path / f"{today}-session-02.json").write_text("{}")
        (tmp_path / "2020-01-01-session-01.json").write_text("{}")
        result = memory_first_enforcer._get_today_session_logs(str(tmp_path))
        assert len(result) == 2

    def test_returns_empty_when_no_match(self, tmp_path):
        (tmp_path / "2020-01-01-session-01.json").write_text("{}")
        result = memory_first_enforcer._get_today_session_logs(str(tmp_path))
        assert result == []

    def test_handles_oserror(self, tmp_path):
        with patch("os.listdir", side_effect=OSError("denied")):
            result = memory_first_enforcer._get_today_session_logs(str(tmp_path))
            assert result == []


class TestTestMemoryEvidence:
    """Tests for _test_memory_evidence."""

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
        result = memory_first_enforcer._test_memory_evidence(str(session_log))
        assert result["complete"] is True
        assert "memory-index" in result["evidence"]

    def test_missing_protocol_compliance(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text(json.dumps({"notes": "stuff"}))
        result = memory_first_enforcer._test_memory_evidence(str(session_log))
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
        result = memory_first_enforcer._test_memory_evidence(str(session_log))
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
        result = memory_first_enforcer._test_memory_evidence(str(session_log))
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
        result = memory_first_enforcer._test_memory_evidence(str(session_log))
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
        result = memory_first_enforcer._test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "empty" in result["reason"]

    def test_invalid_json(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("not valid json {{{")
        result = memory_first_enforcer._test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "invalid JSON" in result["reason"]

    def test_permission_error(self, tmp_path):
        session_log = tmp_path / "session.json"
        session_log.write_text("{}")
        os.chmod(session_log, 0o000)
        try:
            result = memory_first_enforcer._test_memory_evidence(str(session_log))
            assert result["complete"] is False
        finally:
            os.chmod(session_log, 0o644)

    def test_file_not_found(self, tmp_path):
        result = memory_first_enforcer._test_memory_evidence(
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
        result = memory_first_enforcer._test_memory_evidence(str(session_log))
        assert result["complete"] is False


class TestInvocationCount:
    """Tests for _get_invocation_count and _increment_invocation_count."""

    def test_returns_zero_when_no_file(self, tmp_path):
        count = memory_first_enforcer._get_invocation_count(
            str(tmp_path), "2026-03-01"
        )
        assert count == 0

    def test_increments_count(self, tmp_path):
        state_dir = str(tmp_path / "state")
        count = memory_first_enforcer._increment_invocation_count(
            state_dir, "2026-03-01"
        )
        assert count == 1
        count = memory_first_enforcer._increment_invocation_count(
            state_dir, "2026-03-01"
        )
        assert count == 2

    def test_resets_on_new_day(self, tmp_path):
        state_dir = str(tmp_path / "state")
        memory_first_enforcer._increment_invocation_count(
            state_dir, "2026-03-01"
        )
        memory_first_enforcer._increment_invocation_count(
            state_dir, "2026-03-01"
        )
        # New day should reset
        count = memory_first_enforcer._get_invocation_count(
            state_dir, "2026-03-02"
        )
        assert count == 0

    def test_handles_legacy_format(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        state_file = state_dir / "memory-first-counter.txt"
        state_file.write_text("5")
        count = memory_first_enforcer._get_invocation_count(
            str(state_dir), "2026-03-01"
        )
        assert count == 5

    def test_handles_corrupt_file(self, tmp_path):
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        state_file = state_dir / "memory-first-counter.txt"
        state_file.write_text("not a number")
        count = memory_first_enforcer._get_invocation_count(
            str(state_dir), "2026-03-01"
        )
        assert count == 0


class TestMain:
    """Tests for main() entry point."""

    def test_no_session_logs_outputs_guidance(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        # No sessions dir
        result = memory_first_enforcer.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "ADR-007 Memory-First Protocol" in captured.out

    def test_complete_evidence_outputs_verified(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        log_file = sessions_dir / f"{today}-session-01.json"
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
        result = memory_first_enforcer.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Evidence verified" in captured.out

    def test_missing_evidence_education_phase(
        self, monkeypatch, tmp_path, capsys
    ):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        state_dir = tmp_path / ".agents" / ".hook-state"
        state_dir.mkdir(parents=True)
        today = datetime.date.today().strftime("%Y-%m-%d")
        log_file = sessions_dir / f"{today}-session-01.json"
        log_file.write_text(json.dumps({"notes": "incomplete"}))

        result = memory_first_enforcer.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "Warning 1/3" in captured.out

    def test_missing_evidence_escalation_phase(
        self, monkeypatch, tmp_path, capsys
    ):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        state_dir = tmp_path / ".agents" / ".hook-state"
        state_dir.mkdir(parents=True)
        today = datetime.date.today().strftime("%Y-%m-%d")

        # Pre-set counter past threshold
        counter_file = state_dir / "memory-first-counter.txt"
        counter_file.write_text(f"3\n{today}")

        log_file = sessions_dir / f"{today}-session-01.json"
        log_file.write_text(json.dumps({"notes": "incomplete"}))

        result = memory_first_enforcer.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "past threshold" in captured.out

    def test_fails_open_on_exception(self, monkeypatch, capsys):
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/nonexistent/path")
        with patch.object(
            memory_first_enforcer, "_get_today_session_logs",
            side_effect=Exception("unexpected"),
        ):
            result = memory_first_enforcer.main()
        assert result == 0


class TestSessionLogsBranches:
    """Branch coverage for session log edge cases."""

    def test_directory_entry_not_file(self, tmp_path):
        """When a directory matches session log pattern, it is skipped."""
        today = datetime.date.today().strftime("%Y-%m-%d")
        subdir = tmp_path / f"{today}-session-01.json"
        subdir.mkdir()
        result = memory_first_enforcer._get_today_session_logs(str(tmp_path))
        assert result == []


class TestMemoryEvidenceOSError:
    """Tests for _test_memory_evidence OSError handling."""

    def test_permission_error_returns_incomplete(self, tmp_path):
        """PermissionError is caught by the PermissionError handler."""
        session_log = tmp_path / "session.json"
        session_log.write_text("{}")
        os.chmod(session_log, 0o000)
        try:
            result = memory_first_enforcer._test_memory_evidence(str(session_log))
            assert result["complete"] is False
        finally:
            os.chmod(session_log, 0o644)

    def test_generic_oserror_returns_incomplete(self, tmp_path):
        """Generic OSError (not PermissionError/FileNotFoundError) hits the OSError handler."""
        session_log = tmp_path / "session.json"
        session_log.write_text("{}")
        # Raise a base OSError that is not PermissionError or FileNotFoundError
        with patch("builtins.open", side_effect=OSError("generic io error")):
            result = memory_first_enforcer._test_memory_evidence(str(session_log))
        assert result["complete"] is False
        assert "Error parsing session log" in result["reason"]


class TestModuleAsScript:
    """Test that the hook can be executed as a script via __main__."""

    def test_memory_first_enforcer_as_script(self):
        import subprocess

        hook_path = str(
            Path(__file__).resolve().parents[2]
            / ".claude" / "hooks" / "SessionStart" / "memory_first_enforcer.py"
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
            / ".claude" / "hooks" / "SessionStart" / "memory_first_enforcer.py"
        )
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parents[2]))
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(hook_path, run_name="__main__")
        assert exc_info.value.code == 0
