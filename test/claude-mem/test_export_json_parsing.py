"""Tests for JSON parsing error handling in export_claude_mem_direct.

Validates that:
- Valid JSON is parsed correctly
- Corrupted/invalid JSON returns empty list and logs a warning
- Empty string returns empty list
- The warning includes raw output preview (first 200 chars)
- Partial export still saves successfully when some queries return bad JSON
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

SCRIPTS_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / ".claude-mem"
    / "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

from export_claude_mem_direct import _parse_json_output


class TestParseJsonOutput:
    """Tests for the _parse_json_output helper."""

    def test_valid_json_array(self) -> None:
        """Valid JSON array is parsed and returned."""
        raw = '[{"id": 1, "title": "test"}]'
        result = _parse_json_output(raw, "observations")
        assert result == [{"id": 1, "title": "test"}]

    def test_empty_json_array(self) -> None:
        """Empty JSON array returns empty list."""
        result = _parse_json_output("[]", "observations")
        assert result == []

    def test_corrupted_json_returns_empty_list(self) -> None:
        """Corrupted JSON returns empty list instead of crashing."""
        raw = '{not valid json at all'
        result = _parse_json_output(raw, "observations")
        assert result == []

    def test_truncated_json_returns_empty_list(self) -> None:
        """Truncated JSON (partial write) returns empty list."""
        raw = '[{"id": 1, "title": "tes'
        result = _parse_json_output(raw, "observations")
        assert result == []

    def test_corrupted_json_logs_warning_to_stderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Corrupted JSON logs a warning with the label and raw preview."""
        raw = "SQLITE_ERROR: database is corrupted"
        _parse_json_output(raw, "observations")
        captured = capsys.readouterr()
        assert "WARNING: Failed to parse observations JSON" in captured.err
        assert "SQLITE_ERROR: database is corrupted" in captured.err

    def test_corrupted_json_preview_truncated_at_200_chars(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Raw output preview is truncated to 200 characters."""
        raw = "x" * 500
        _parse_json_output(raw, "sessions")
        captured = capsys.readouterr()
        # The preview should contain exactly 200 x's, not 500
        assert "x" * 200 in captured.err
        assert "x" * 201 not in captured.err

    def test_empty_raw_string_logs_empty_marker(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Empty raw string shows '(empty)' in the preview."""
        _parse_json_output("", "prompts")
        captured = capsys.readouterr()
        assert "(empty)" in captured.err

    def test_binary_garbage_returns_empty_list(self) -> None:
        """Binary-like garbage data returns empty list."""
        raw = "\x00\x01\x02\xff\xfe"
        result = _parse_json_output(raw, "sessions")
        assert result == []

    def test_html_error_page_returns_empty_list(self) -> None:
        """HTML error output (wrong content type) returns empty list."""
        raw = "<html><body>500 Internal Server Error</body></html>"
        result = _parse_json_output(raw, "observations")
        assert result == []

    def test_valid_json_object_not_array(self) -> None:
        """A valid JSON object (not array) is returned as-is.

        sqlite3 -json always returns arrays, but the parser should not crash
        on unexpected shapes.
        """
        raw = '{"key": "value"}'
        result = _parse_json_output(raw, "observations")
        assert result == {"key": "value"}


class TestMainWithCorruptedOutput:
    """Integration tests: main() handles corrupted sqlite3 output gracefully."""

    @pytest.fixture
    def mock_env(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        """Set up a mock environment with a fake database file."""
        db_dir = tmp_path / ".claude-mem"
        db_dir.mkdir()
        db_file = db_dir / "claude-mem.db"
        db_file.write_text("")  # empty file, we mock sqlite3 calls

        memories_dir = tmp_path / "memories"
        memories_dir.mkdir()

        # Point _SCRIPT_DIR to tmp so security script path won't exist
        script_dir = tmp_path / "scripts"
        script_dir.mkdir()

        return db_file, memories_dir, script_dir

    def _make_completed_process(
        self, stdout: str, returncode: int = 0
    ) -> CompletedProcess[str]:
        return CompletedProcess(
            args=["sqlite3"], returncode=returncode, stdout=stdout, stderr=""
        )

    def test_partial_export_saves_when_one_query_returns_bad_json(
        self, mock_env: tuple[Path, Path, Path]
    ) -> None:
        """When one table returns corrupted JSON, other tables still export."""
        db_file, memories_dir, script_dir = mock_env
        output_file = memories_dir / "test-export.json"

        valid_obs = json.dumps([{"id": 1, "title": "test obs"}])
        corrupted_summaries = "NOT VALID JSON"
        valid_prompts = json.dumps([{"prompt_number": 1, "content": "hello"}])
        valid_sessions = json.dumps([{"content_session_id": "abc"}])

        call_count = {"n": 0}
        responses = [
            # get_count calls (4 calls, return "1" for each)
            self._make_completed_process("1\n"),
            self._make_completed_process("1\n"),
            self._make_completed_process("1\n"),
            self._make_completed_process("1\n"),
            # Data queries: observations, summaries (corrupted), prompts, sessions
            self._make_completed_process(valid_obs),
            self._make_completed_process(corrupted_summaries),
            self._make_completed_process(valid_prompts),
            self._make_completed_process(valid_sessions),
        ]

        def mock_run(
            db_path: str, query: str, json_mode: bool = False
        ) -> CompletedProcess[str]:
            idx = call_count["n"]
            call_count["n"] += 1
            return responses[idx]

        from export_claude_mem_direct import main

        with (
            patch("export_claude_mem_direct.run_sqlite3", side_effect=mock_run),
            patch("export_claude_mem_direct.Path.home", return_value=db_file.parent.parent),
            patch("export_claude_mem_direct._MEMORIES_DIR", memories_dir),
            patch("export_claude_mem_direct._SCRIPT_DIR", script_dir),
            patch("export_claude_mem_direct.validate_output_path", return_value=True),
            patch("shutil.which", return_value="/usr/bin/sqlite3"),
        ):
            exit_code = main(["--output-file", str(output_file)])

        assert exit_code == 0
        assert output_file.exists()

        export_data = json.loads(output_file.read_text())
        assert len(export_data["observations"]) == 1
        assert export_data["summaries"] == []  # corrupted, falls back to empty
        assert len(export_data["prompts"]) == 1
        assert len(export_data["sessions"]) == 1

    def test_all_corrupted_still_saves_empty_export(
        self, mock_env: tuple[Path, Path, Path]
    ) -> None:
        """When all queries return corrupted JSON, export still saves with empty arrays."""
        db_file, memories_dir, script_dir = mock_env
        output_file = memories_dir / "test-export.json"

        call_count = {"n": 0}
        responses = [
            # 4 count queries
            self._make_completed_process("0\n"),
            self._make_completed_process("0\n"),
            self._make_completed_process("0\n"),
            self._make_completed_process("0\n"),
            # 4 data queries, all corrupted
            self._make_completed_process("CORRUPT1"),
            self._make_completed_process("CORRUPT2"),
            self._make_completed_process("CORRUPT3"),
            self._make_completed_process("CORRUPT4"),
        ]

        def mock_run(
            db_path: str, query: str, json_mode: bool = False
        ) -> CompletedProcess[str]:
            idx = call_count["n"]
            call_count["n"] += 1
            return responses[idx]

        from export_claude_mem_direct import main

        with (
            patch("export_claude_mem_direct.run_sqlite3", side_effect=mock_run),
            patch("export_claude_mem_direct.Path.home", return_value=db_file.parent.parent),
            patch("export_claude_mem_direct._MEMORIES_DIR", memories_dir),
            patch("export_claude_mem_direct._SCRIPT_DIR", script_dir),
            patch("export_claude_mem_direct.validate_output_path", return_value=True),
            patch("shutil.which", return_value="/usr/bin/sqlite3"),
        ):
            exit_code = main(["--output-file", str(output_file)])

        assert exit_code == 0
        assert output_file.exists()

        export_data = json.loads(output_file.read_text())
        assert export_data["observations"] == []
        assert export_data["summaries"] == []
        assert export_data["prompts"] == []
        assert export_data["sessions"] == []

    def test_corrupted_output_produces_stderr_warnings(
        self, mock_env: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Corrupted JSON produces clear warning messages on stderr."""
        db_file, memories_dir, script_dir = mock_env
        output_file = memories_dir / "test-export.json"

        call_count = {"n": 0}
        responses = [
            self._make_completed_process("1\n"),
            self._make_completed_process("1\n"),
            self._make_completed_process("1\n"),
            self._make_completed_process("1\n"),
            # observations: corrupted with recognizable content
            self._make_completed_process("Error: database disk image is malformed"),
            # summaries, prompts, sessions: valid empty
            self._make_completed_process("[]"),
            self._make_completed_process("[]"),
            self._make_completed_process("[]"),
        ]

        def mock_run(
            db_path: str, query: str, json_mode: bool = False
        ) -> CompletedProcess[str]:
            idx = call_count["n"]
            call_count["n"] += 1
            return responses[idx]

        from export_claude_mem_direct import main

        with (
            patch("export_claude_mem_direct.run_sqlite3", side_effect=mock_run),
            patch("export_claude_mem_direct.Path.home", return_value=db_file.parent.parent),
            patch("export_claude_mem_direct._MEMORIES_DIR", memories_dir),
            patch("export_claude_mem_direct._SCRIPT_DIR", script_dir),
            patch("export_claude_mem_direct.validate_output_path", return_value=True),
            patch("shutil.which", return_value="/usr/bin/sqlite3"),
        ):
            main(["--output-file", str(output_file)])

        captured = capsys.readouterr()
        assert "WARNING: Failed to parse observations JSON" in captured.err
        assert "database disk image is malformed" in captured.err
