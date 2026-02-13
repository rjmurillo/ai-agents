#!/usr/bin/env python3
"""Tests for SessionStart/invoke_memory_first_enforcer.py."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add hook directory to path for import
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "SessionStart"),
)

import invoke_memory_first_enforcer as hook


class TestTestMemoryEvidence:
    """Tests for test_memory_evidence()."""

    def test_complete_evidence(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text(
            json.dumps(
                {
                    "protocolCompliance": {
                        "sessionStart": {
                            "serenaActivated": {"complete": True},
                            "handoffRead": {"complete": True},
                            "memoriesLoaded": {
                                "complete": True,
                                "Evidence": "memory-index, project-overview",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = hook.test_memory_evidence(str(log))
        assert result["complete"] is True
        assert "memory-index" in result["evidence"]

    def test_missing_protocol_compliance(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text(json.dumps({}), encoding="utf-8")
        result = hook.test_memory_evidence(str(log))
        assert result["complete"] is False
        assert "Missing" in result["reason"]

    def test_serena_not_activated(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text(
            json.dumps(
                {
                    "protocolCompliance": {
                        "sessionStart": {
                            "serenaActivated": {"complete": False},
                            "handoffRead": {"complete": True},
                            "memoriesLoaded": {"complete": True, "Evidence": "x"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = hook.test_memory_evidence(str(log))
        assert result["complete"] is False
        assert "Serena" in result["reason"]

    def test_handoff_not_read(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text(
            json.dumps(
                {
                    "protocolCompliance": {
                        "sessionStart": {
                            "serenaActivated": {"complete": True},
                            "handoffRead": {"complete": False},
                            "memoriesLoaded": {"complete": True, "Evidence": "x"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = hook.test_memory_evidence(str(log))
        assert result["complete"] is False
        assert "HANDOFF" in result["reason"]

    def test_empty_evidence(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text(
            json.dumps(
                {
                    "protocolCompliance": {
                        "sessionStart": {
                            "serenaActivated": {"complete": True},
                            "handoffRead": {"complete": True},
                            "memoriesLoaded": {"complete": True, "Evidence": ""},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = hook.test_memory_evidence(str(log))
        assert result["complete"] is False
        assert "empty" in result["reason"]

    def test_invalid_json(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text("not valid json", encoding="utf-8")
        result = hook.test_memory_evidence(str(log))
        assert result["complete"] is False
        assert "invalid JSON" in result["reason"]

    def test_missing_file(self) -> None:
        result = hook.test_memory_evidence("/nonexistent/path/session.json")
        assert result["complete"] is False
        assert "deleted" in result["reason"]

    def test_lowercase_evidence_key(self, tmp_path: Path) -> None:
        """Evidence key can be lowercase 'evidence' per Copilot fix."""
        log = tmp_path / "session.json"
        log.write_text(
            json.dumps(
                {
                    "protocolCompliance": {
                        "sessionStart": {
                            "serenaActivated": {"complete": True},
                            "handoffRead": {"complete": True},
                            "memoriesLoaded": {
                                "complete": True,
                                "evidence": "memory-index",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        result = hook.test_memory_evidence(str(log))
        assert result["complete"] is True


class TestInvocationCounter:
    """Tests for get/increment invocation count."""

    def test_initial_count_is_zero(self, tmp_path: Path) -> None:
        assert hook.get_invocation_count(str(tmp_path), "2026-02-12") == 0

    def test_increment_creates_file(self, tmp_path: Path) -> None:
        count = hook.increment_invocation_count(str(tmp_path), "2026-02-12")
        assert count == 1
        state_file = tmp_path / "memory-first-counter.txt"
        assert state_file.exists()

    def test_increment_accumulates(self, tmp_path: Path) -> None:
        hook.increment_invocation_count(str(tmp_path), "2026-02-12")
        hook.increment_invocation_count(str(tmp_path), "2026-02-12")
        count = hook.increment_invocation_count(str(tmp_path), "2026-02-12")
        assert count == 3

    def test_date_change_resets_counter(self, tmp_path: Path) -> None:
        hook.increment_invocation_count(str(tmp_path), "2026-02-11")
        hook.increment_invocation_count(str(tmp_path), "2026-02-11")
        count = hook.get_invocation_count(str(tmp_path), "2026-02-12")
        assert count == 0

    def test_creates_state_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = str(Path(tmpdir) / "nested" / "state")
            count = hook.increment_invocation_count(state_dir, "2026-02-12")
            assert count == 1
            assert Path(state_dir).is_dir()


class TestMain:
    """Tests for main() entry point."""

    def test_no_session_log_outputs_guidance(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch.object(hook, "get_project_directory", return_value="/tmp/test"),
            patch.object(hook, "get_today_session_logs", return_value=[]),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "/session-init" in captured.out

    def test_complete_evidence_outputs_success(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        log = tmp_path / "2026-02-12-session-01.json"
        log.write_text(
            json.dumps(
                {
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
                }
            ),
            encoding="utf-8",
        )

        with (
            patch.object(hook, "get_project_directory", return_value=str(tmp_path)),
            patch.object(hook, "get_today_session_logs", return_value=[log]),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Evidence verified" in captured.out

    def test_exception_fails_open(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(hook, "get_project_directory", side_effect=RuntimeError("boom")):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "boom" in captured.err

    def test_missing_evidence_shows_warning(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        log = tmp_path / "2026-02-12-session-01.json"
        log.write_text(json.dumps({}), encoding="utf-8")
        state_dir = tmp_path / ".hook-state"
        state_dir.mkdir()

        with (
            patch.object(hook, "get_project_directory", return_value=str(tmp_path)),
            patch.object(hook, "get_today_session_logs", return_value=[log]),
        ):
            result = hook.main()

        assert result == 0
        captured = capsys.readouterr()
        assert "ADR-007" in captured.out
        assert "Warning" in captured.out or "VIOLATION" in captured.out
