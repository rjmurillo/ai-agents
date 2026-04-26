#!/usr/bin/env python3
"""Tests for invoke_false_completion_gate.py (PreToolUse hook)."""

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "PreToolUse"))

import invoke_false_completion_gate


class TestFalseCompletionGate(unittest.TestCase):
    """Test PreToolUse false completion gate."""

    def test_tty_stdin_exits_zero(self):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = invoke_false_completion_gate.main()
            self.assertEqual(result, 0)

    def test_empty_stdin_exits_zero(self):
        with patch("sys.stdin", StringIO("")):
            result = invoke_false_completion_gate.main()
            self.assertEqual(result, 0)

    def test_non_completion_command_passes(self):
        """Regular commands should not be blocked."""
        hook_input = {"tool_input": {"command": "ls -la"}}
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            result = invoke_false_completion_gate.main()
            self.assertEqual(result, 0)

    def test_commit_without_completion_signal_passes(self):
        """git commit without done/fixed keywords passes."""
        hook_input = {"tool_input": {"command": "git commit -m 'refactor: extract method'"}}
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            result = invoke_false_completion_gate.main()
            self.assertEqual(result, 0)

    def test_commit_with_done_no_verification_blocks(self):
        """git commit claiming 'done' without test evidence should block."""
        hook_input = {"tool_input": {"command": "git commit -m 'feat: done with implementation'"}}
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".git").mkdir()
            (tmp_path / ".agents" / "sessions").mkdir(parents=True)

            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch.object(invoke_false_completion_gate, "get_project_directory", return_value=tmp_path):
                    with patch("sys.stdout", new_callable=StringIO) as mock_out:
                        result = invoke_false_completion_gate.main()
                        self.assertEqual(result, 2)
                        output = json.loads(mock_out.getvalue())
                        self.assertEqual(output["decision"], "block")

    def test_commit_with_done_and_verification_passes(self):
        """git commit claiming 'done' WITH test evidence should pass."""
        hook_input = {"tool_input": {"command": "git commit -m 'feat: done with implementation'"}}
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".git").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            from datetime import UTC, datetime
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session_file = sessions_dir / f"{today}-session-01.json"
            # Use the current schema (workLog) and a realistic verification marker
            # that matches both VERIFICATION_PATTERNS (command name) and
            # VERIFICATION_RESULT_PATTERNS (pass/fail count).
            session_file.write_text(json.dumps({
                "workLog": ["ran pytest: 32 passed in 0.21s"]
            }))

            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch.object(invoke_false_completion_gate, "get_project_directory", return_value=tmp_path):
                    result = invoke_false_completion_gate.main()
                    self.assertEqual(result, 0)

    def test_bypass_env_var(self):
        """SKIP_COMPLETION_GATE=true should bypass."""
        hook_input = {"tool_input": {"command": "git commit -m 'done'"}}
        with patch.dict("os.environ", {"SKIP_COMPLETION_GATE": "true"}):
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                result = invoke_false_completion_gate.main()
                self.assertEqual(result, 0)

    def test_pr_create_with_closes_blocks(self):
        """gh pr create with 'closes #X' without verification blocks."""
        hook_input = {"tool_input": {"command": "gh pr create --title 'closes #123'"}}
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".git").mkdir()
            (tmp_path / ".agents" / "sessions").mkdir(parents=True)

            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch.object(invoke_false_completion_gate, "get_project_directory", return_value=tmp_path):
                    with patch("sys.stdout", new_callable=StringIO):
                        result = invoke_false_completion_gate.main()
                        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
