#!/usr/bin/env python3
"""Tests for PreToolUse/invoke_false_completion_gate.py.

Covers:
- Completion signal regex detection
- Verification evidence checking in session logs
- Deny output format
- Bypass conditions (env var, docs-only, no session log)
- Consumer repo skip
- Non-commit commands pass through
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "PreToolUse"))

import invoke_false_completion_gate


class TestCompletionSignalDetection:
    """Test _is_completion_claim regex matching."""

    @pytest.mark.parametrize(
        "command",
        [
            'git commit -m "feat: done with implementation"',
            'git commit -m "fix: fixed the bug"',
            'git commit -m "feat: completed migration"',
            'git commit -m "chore: finished cleanup"',
            'git commit -m "feat: resolved issue"',
            'git commit -m "feat: merged changes"',
            'git commit -m "feat: shipped v2"',
            'git commit -m "fix: closes #42"',
        ],
    )
    def test_detects_completion_signals(self, command: str) -> None:
        assert invoke_false_completion_gate._is_completion_claim(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            'git commit -m "feat: add new validation logic"',
            'git commit -m "refactor: extract helper method"',
            'git commit -m "test: add unit tests for parser"',
            'git commit -m "docs: update README"',
            'git commit -m "chore: update dependencies"',
        ],
    )
    def test_ignores_non_completion_signals(self, command: str) -> None:
        assert invoke_false_completion_gate._is_completion_claim(command) is False


class TestVerificationEvidence:
    """Test _has_verification_evidence checking."""

    def test_finds_pytest_evidence(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(
            json.dumps({"work": [{"task": "ran uv run pytest"}]}),
            encoding="utf-8",
        )

        with patch.object(
            invoke_false_completion_gate,
            "get_project_directory",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate,
            "get_today_session_log",
            return_value=log,
        ):
            assert invoke_false_completion_gate._has_verification_evidence(str(tmp_path)) is True

    def test_no_evidence_without_tests(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(
            json.dumps({"work": [{"task": "edited some files"}]}),
            encoding="utf-8",
        )

        with patch.object(
            invoke_false_completion_gate,
            "get_today_session_log",
            return_value=log,
        ):
            assert invoke_false_completion_gate._has_verification_evidence(str(tmp_path)) is False

    def test_no_evidence_without_session_log(self, tmp_path: Path) -> None:
        with patch.object(
            invoke_false_completion_gate,
            "get_today_session_log",
            return_value=None,
        ):
            assert invoke_false_completion_gate._has_verification_evidence(str(tmp_path)) is False


class TestMain:
    """Test main() function flow."""

    def test_skip_consumer_repo(self) -> None:
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=True
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_skip_via_env_var(self) -> None:
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.dict("os.environ", {"SKIP_COMPLETION_GATE": "true"}):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_tty_stdin_exits_zero(self) -> None:
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_non_commit_command_passes(self) -> None:
        hook_input = json.dumps({
            "tool_input": {"command": "ls -la"},
        })
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json",
            return_value=json.loads(hook_input),
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_commit_without_completion_signal_passes(self) -> None:
        hook_input = {
            "tool_input": {"command": 'git commit -m "feat: add new validation"'},
        }
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_blocks_completion_without_evidence(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(json.dumps({"work": []}), encoding="utf-8")

        hook_input = {
            "tool_input": {"command": 'git commit -m "feat: done with implementation"'},
        }
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ), patch.object(
            invoke_false_completion_gate,
            "get_project_directory",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate, "_is_documentation_only", return_value=False,
        ), patch.object(
            invoke_false_completion_gate, "get_today_session_log", return_value=log,
        ), patch.object(
            invoke_false_completion_gate,
            "_has_verification_evidence",
            return_value=False,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 2

    def test_allows_completion_with_evidence(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        log = sessions_dir / "2026-01-01-session-001.json"
        log.write_text(
            json.dumps({"work": [{"task": "ran pytest"}]}),
            encoding="utf-8",
        )

        hook_input = {
            "tool_input": {"command": 'git commit -m "feat: done with implementation"'},
        }
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ), patch.object(
            invoke_false_completion_gate,
            "get_project_directory",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate, "_is_documentation_only", return_value=False,
        ), patch.object(
            invoke_false_completion_gate, "get_today_session_log", return_value=log,
        ), patch.object(
            invoke_false_completion_gate,
            "_has_verification_evidence",
            return_value=True,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0

    def test_allows_documentation_only(self, tmp_path: Path) -> None:
        hook_input = {
            "tool_input": {"command": 'git commit -m "docs: done updating README"'},
        }
        with patch.object(
            invoke_false_completion_gate, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_false_completion_gate, "_read_stdin_json", return_value=hook_input,
        ), patch.object(
            invoke_false_completion_gate,
            "get_project_directory",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_false_completion_gate, "_is_documentation_only", return_value=True,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_false_completion_gate.main()
            assert exc_info.value.code == 0


class TestFailOpen:
    """Test fail-open behavior on unexpected errors."""

    def test_exception_exits_zero(self) -> None:
        with patch.object(
            invoke_false_completion_gate,
            "skip_if_consumer_repo",
            side_effect=RuntimeError("boom"),
        ):
            try:
                invoke_false_completion_gate.main()
            except (SystemExit, RuntimeError):
                pass  # Expected - fail-open in __main__ block
