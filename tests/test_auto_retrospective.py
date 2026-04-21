#!/usr/bin/env python3
"""Tests for invoke_auto_retrospective.py (Stop hook)."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "Stop"))

import invoke_auto_retrospective


class TestAutoRetrospective(unittest.TestCase):
    """Test Stop auto-retrospective hook."""

    def test_tty_stdin_exits_zero(self):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = invoke_auto_retrospective.main()
            self.assertEqual(result, 0)

    def test_bypass_env_var(self):
        with patch.dict("os.environ", {"SKIP_AUTO_RETRO": "true"}):
            with patch("sys.stdin", StringIO("")):
                result = invoke_auto_retrospective.main()
                self.assertEqual(result, 0)

    def test_skips_if_retro_exists_today(self):
        """Should not create duplicate retros."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            retro_dir = tmp_path / ".agents" / "retrospective"
            retro_dir.mkdir(parents=True)
            today = datetime.now().strftime("%Y-%m-%d")
            existing = retro_dir / f"{today}-manual-retro.md"
            existing.write_text("# Already exists")

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_auto_retrospective, "get_project_directory", return_value=tmp_path):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)
                    # No new file created
                    files = list(retro_dir.glob("*.md"))
                    self.assertEqual(len(files), 1)

    def test_skips_trivial_sessions(self):
        """Should not generate retro for trivial sessions."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now().strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(json.dumps({"work": [], "outcomes": []}))

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_auto_retrospective, "get_project_directory", return_value=tmp_path):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)

    def test_generates_retro_for_nontrivial_session(self):
        """Should generate retro when session has work items."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now().strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(json.dumps({
                "work": ["Implemented feature X"],
                "outcomes": ["PR created"]
            }))

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_auto_retrospective, "get_project_directory", return_value=tmp_path):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)

                    # Retro file created
                    retro_dir = tmp_path / ".agents" / "retrospective"
                    retros = list(retro_dir.glob(f"{today}*.md"))
                    self.assertEqual(len(retros), 1)
                    content = retros[0].read_text()
                    self.assertIn("Implemented feature X", content)

                    # INDEX.md updated
                    index = tmp_path / "docs" / "retros" / "INDEX.md"
                    self.assertTrue(index.exists())
                    self.assertIn(today, index.read_text())

    def test_fail_open_on_os_error(self):
        """OSError should not crash the hook."""
        with patch("sys.stdin", StringIO("")):
            with patch.object(invoke_auto_retrospective, "get_project_directory", return_value=Path("/nonexistent/path")):
                result = invoke_auto_retrospective.main()
                self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
