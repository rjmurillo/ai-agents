#!/usr/bin/env python3
"""Tests for invoke_plan_state_sync.py (PostToolUse hook)."""

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "PostToolUse"))

import invoke_plan_state_sync


class TestPlanStateSync(unittest.TestCase):
    """Test PostToolUse plan state sync hook."""

    def test_tty_stdin_exits_zero(self):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = invoke_plan_state_sync.main()
            self.assertEqual(result, 0)

    def test_empty_stdin_exits_zero(self):
        with patch("sys.stdin", StringIO("")):
            result = invoke_plan_state_sync.main()
            self.assertEqual(result, 0)

    def test_non_plan_file_passes_through(self):
        """Regular files should not trigger checkpointing."""
        hook_input = {"tool_input": {"file_path": "src/main.py"}}
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            result = invoke_plan_state_sync.main()
            self.assertEqual(result, 0)

    def test_session_log_triggers_checkpoint(self):
        """Session log writes should create checkpoint."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".git").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            session_file = sessions_dir / "2026-04-20-session-01.json"
            session_file.write_text(json.dumps({"work": ["task A"]}))

            hook_input = {"tool_input": {"file_path": ".agents/sessions/2026-04-20-session-01.json"}}
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch.object(invoke_plan_state_sync, "get_project_directory", return_value=tmp_path):
                    result = invoke_plan_state_sync.main()
                    self.assertEqual(result, 0)

                    # Checkpoint should exist
                    hook_state = tmp_path / ".agents" / ".hook-state"
                    checkpoints = list(hook_state.glob("plan-checkpoint-*.json"))
                    self.assertEqual(len(checkpoints), 1)

    def test_todo_md_triggers_checkpoint(self):
        """TODO.md writes should create checkpoint."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".git").mkdir()
            todo = tmp_path / "TODO.md"
            todo.write_text("- [ ] Fix bug")

            hook_input = {"tool_input": {"file_path": "TODO.md"}}
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch.object(invoke_plan_state_sync, "get_project_directory", return_value=tmp_path):
                    result = invoke_plan_state_sync.main()
                    self.assertEqual(result, 0)

                    hook_state = tmp_path / ".agents" / ".hook-state"
                    checkpoints = list(hook_state.glob("plan-checkpoint-*.json"))
                    self.assertEqual(len(checkpoints), 1)

    def test_checkpoint_contains_summary(self):
        """Checkpoint should contain first 500 chars of file."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".git").mkdir()
            todo = tmp_path / "TODO.md"
            todo.write_text("Important task details here")

            hook_input = {"tool_input": {"file_path": "TODO.md"}}
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch.object(invoke_plan_state_sync, "get_project_directory", return_value=tmp_path):
                    invoke_plan_state_sync.main()

                    hook_state = tmp_path / ".agents" / ".hook-state"
                    cp = list(hook_state.glob("plan-checkpoint-*.json"))[0]
                    data = json.loads(cp.read_text())
                    self.assertIn("Important task details", data[-1]["summary"])


if __name__ == "__main__":
    unittest.main()
