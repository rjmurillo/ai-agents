#!/usr/bin/env python3
"""Tests for invoke_compact_checkpoint.py (PreCompact hook)."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "PreCompact"))

import invoke_compact_checkpoint


class TestCompactCheckpoint(unittest.TestCase):
    """Test PreCompact checkpoint hook."""

    def test_tty_stdin_exits_zero(self):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = invoke_compact_checkpoint.main()
            self.assertEqual(result, 0)

    def test_creates_checkpoint_file(self):
        """Should create checkpoint JSON in .hook-state."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".git").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now().strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(json.dumps({"work": ["task A", "task B"]}))

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_compact_checkpoint, "get_project_directory", return_value=tmp_path):
                    with patch.object(invoke_compact_checkpoint, "get_current_branch", return_value="feature/1703"):
                        with patch("sys.stdout", new_callable=StringIO) as mock_out:
                            result = invoke_compact_checkpoint.main()
                            self.assertEqual(result, 0)

                            # Checkpoint file exists
                            hook_state = tmp_path / ".agents" / ".hook-state"
                            checkpoints = list(hook_state.glob("pre-compact-*.json"))
                            self.assertEqual(len(checkpoints), 1)

                            # Content is valid
                            data = json.loads(checkpoints[0].read_text())
                            self.assertEqual(data["branch"], "feature/1703")
                            self.assertIn("session", data)

                            # Resume context printed to stdout
                            output = mock_out.getvalue()
                            self.assertIn("feature/1703", output)
                            self.assertIn("Compaction occurred", output)

    def test_fail_open_on_git_error(self):
        """Should not crash if git is unavailable."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".git").mkdir()

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_compact_checkpoint, "get_project_directory", return_value=tmp_path):
                    with patch("subprocess.run", side_effect=FileNotFoundError):
                        with patch("sys.stdout", new_callable=StringIO):
                            result = invoke_compact_checkpoint.main()
                            self.assertEqual(result, 0)

    def test_no_project_dir_exits_zero(self):
        with patch("sys.stdin", StringIO("")):
            with patch.object(invoke_compact_checkpoint, "get_project_directory", return_value=None):
                result = invoke_compact_checkpoint.main()
                self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
