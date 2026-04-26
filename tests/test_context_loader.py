#!/usr/bin/env python3
"""Tests for invoke_context_loader.py (SessionStart hook)."""

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "SessionStart"))

import invoke_context_loader


class TestContextLoader(unittest.TestCase):
    """Test SessionStart context loader hook."""

    def test_tty_stdin_exits_zero(self):
        """TTY stdin should exit 0 immediately."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = invoke_context_loader.main()
            self.assertEqual(result, 0)

    def test_no_project_dir_exits_zero(self):
        """Missing project dir should fail-open."""
        with patch("sys.stdin", StringIO("")):
            with patch.object(invoke_context_loader, "get_project_directory", return_value=None):
                result = invoke_context_loader.main()
                self.assertEqual(result, 0)

    def test_loads_handoff_md(self):
        """HANDOFF.md content should be printed to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            agents_dir = tmp_path / ".agents"
            agents_dir.mkdir()
            handoff = agents_dir / "HANDOFF.md"
            handoff.write_text("# Handoff\nCurrent work: feature X")

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_context_loader, "get_project_directory", return_value=tmp_path):
                    with patch("sys.stdout", new_callable=StringIO) as mock_out:
                        result = invoke_context_loader.main()
                        self.assertEqual(result, 0)
                        self.assertIn("HANDOFF.md", mock_out.getvalue())
                        self.assertIn("feature X", mock_out.getvalue())

    def test_loads_latest_retro(self):
        """Latest retrospective should be printed to stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            retro_dir = tmp_path / ".agents" / "retrospective"
            retro_dir.mkdir(parents=True)
            retro = retro_dir / "2026-04-20-retro.md"
            retro.write_text("# Retro\nLearning: test first")

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_context_loader, "get_project_directory", return_value=tmp_path):
                    with patch("sys.stdout", new_callable=StringIO) as mock_out:
                        result = invoke_context_loader.main()
                        self.assertEqual(result, 0)
                        self.assertIn("test first", mock_out.getvalue())

    def test_truncates_large_files(self):
        """Files exceeding MAX_CHARS_PER_FILE should be truncated."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            agents_dir = tmp_path / ".agents"
            agents_dir.mkdir()
            handoff = agents_dir / "HANDOFF.md"
            handoff.write_text("X" * 10000)

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_context_loader, "get_project_directory", return_value=tmp_path):
                    with patch("sys.stdout", new_callable=StringIO) as mock_out:
                        invoke_context_loader.main()
                        # Should be truncated to MAX_CHARS_PER_FILE + header
                        output = mock_out.getvalue()
                        x_count = output.count("X")
                        self.assertLessEqual(x_count, invoke_context_loader.MAX_CHARS_PER_FILE)

    def test_fail_open_on_missing_files(self):
        """Missing HANDOFF.md and retro dir should not error."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # No .agents dir at all

            with patch("sys.stdin", StringIO("")):
                with patch.object(invoke_context_loader, "get_project_directory", return_value=tmp_path):
                    result = invoke_context_loader.main()
                    self.assertEqual(result, 0)


class TestGetLatestRetrospective(unittest.TestCase):
    """Test retrospective file discovery."""

    def test_returns_none_for_missing_dir(self):
        result = invoke_context_loader.get_latest_retrospective(Path("/nonexistent"))
        self.assertIsNone(result)

    def test_returns_most_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            old = tmp_path / "2026-01-01-retro.md"
            new = tmp_path / "2026-04-20-retro.md"
            old.write_text("old")
            new.write_text("new")
            # Set mtimes explicitly so ordering is deterministic across filesystems
            import os
            os.utime(old, (1_000_000_000, 1_000_000_000))
            os.utime(new, (1_000_000_100, 1_000_000_100))

            result = invoke_context_loader.get_latest_retrospective(tmp_path)
            self.assertEqual(result, new)


if __name__ == "__main__":
    unittest.main()
