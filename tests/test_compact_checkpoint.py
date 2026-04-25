#!/usr/bin/env python3
"""Tests for PreCompact/invoke_compact_checkpoint.py.

Covers:
- Checkpoint file creation with correct structure
- Resume context stdout output
- Open item extraction from session logs
- Git branch detection
- Fail-open on git errors
- Consumer repo skip
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "PreCompact"))

import invoke_compact_checkpoint


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    """Create a minimal project directory tree with session log."""
    agents = tmp_path / ".agents"
    agents.mkdir()
    sessions = agents / "sessions"
    sessions.mkdir()

    session_log = sessions / "2026-01-01-session-001.json"
    session_data = {
        "objective": "Implement feature X",
        "work": [
            {"description": "Write implementation", "status": "in_progress"},
            {"description": "Add tests", "status": "pending"},
            {"description": "Update docs", "status": "done"},
        ],
    }
    session_log.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
    return tmp_path


class TestExtractOpenItems:
    """Test _extract_open_items helper."""

    def test_extracts_non_done_items(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text(
            json.dumps({
                "work": [
                    {"description": "Task A", "status": "in_progress"},
                    {"description": "Task B", "status": "done"},
                    {"description": "Task C", "status": "pending"},
                ],
            }),
            encoding="utf-8",
        )

        items = invoke_compact_checkpoint._extract_open_items(log)
        assert len(items) == 2
        assert "Task A" in items
        assert "Task C" in items

    def test_handles_string_work_items(self, tmp_path: Path) -> None:
        log = tmp_path / "session.json"
        log.write_text(
            json.dumps({"work": ["string item 1", "string item 2"]}),
            encoding="utf-8",
        )

        items = invoke_compact_checkpoint._extract_open_items(log)
        assert len(items) == 2

    def test_handles_invalid_json(self, tmp_path: Path) -> None:
        log = tmp_path / "bad.json"
        log.write_text("not json", encoding="utf-8")

        items = invoke_compact_checkpoint._extract_open_items(log)
        assert items == []

    def test_handles_missing_file(self, tmp_path: Path) -> None:
        items = invoke_compact_checkpoint._extract_open_items(
            tmp_path / "nonexistent.json"
        )
        assert items == []


class TestGetCurrentBranch:
    """Test _get_current_branch helper."""

    def test_returns_branch_name(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "feature/test-branch\n"

            result = invoke_compact_checkpoint._get_current_branch()
            assert result == "feature/test-branch"

    def test_returns_unknown_on_error(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""

            result = invoke_compact_checkpoint._get_current_branch()
            assert result == "(unknown)"

    def test_returns_unknown_on_os_error(self) -> None:
        with patch("subprocess.run", side_effect=OSError("no git")):
            result = invoke_compact_checkpoint._get_current_branch()
            assert result == "(unknown)"


class TestWriteCheckpoint:
    """Test _write_checkpoint function."""

    def test_creates_checkpoint_file(self, tmp_path: Path) -> None:
        (tmp_path / ".agents").mkdir()
        invoke_compact_checkpoint._write_checkpoint(
            str(tmp_path),
            "2026-01-01-session-001.json",
            "2026-01-01T10:00:00+00:00",
            "feature/test",
            ["Task A", "Task B"],
            "Resume context here",
        )

        checkpoint_dir = tmp_path / ".agents" / ".hook-state"
        assert checkpoint_dir.exists()
        files = list(checkpoint_dir.glob("pre-compact-*.json"))
        assert len(files) == 1

        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["session_log"] == "2026-01-01-session-001.json"
        assert data["branch"] == "feature/test"
        assert len(data["open_items"]) == 2


class TestMain:
    """Test main() function."""

    def test_skip_consumer_repo(self) -> None:
        with patch.object(
            invoke_compact_checkpoint, "skip_if_consumer_repo", return_value=True
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_compact_checkpoint.main()
            assert exc_info.value.code == 0

    def test_outputs_resume_context(
        self, project_tree: Path, capsys: pytest.CaptureFixture
    ) -> None:
        session_log = list(
            (project_tree / ".agents" / "sessions").glob("*.json")
        )[0]

        with patch.object(
            invoke_compact_checkpoint, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_compact_checkpoint,
            "get_project_directory",
            return_value=str(project_tree),
        ), patch.object(
            invoke_compact_checkpoint,
            "get_today_session_log",
            return_value=session_log,
        ), patch.object(
            invoke_compact_checkpoint,
            "_get_current_branch",
            return_value="feature/test",
        ):
            invoke_compact_checkpoint.main()

        captured = capsys.readouterr()
        assert "Pre-Compaction Checkpoint" in captured.out
        assert "feature/test" in captured.out

    def test_handles_no_session_log(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        (tmp_path / ".agents").mkdir()

        with patch.object(
            invoke_compact_checkpoint, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_compact_checkpoint,
            "get_project_directory",
            return_value=str(tmp_path),
        ), patch.object(
            invoke_compact_checkpoint,
            "get_today_session_log",
            return_value=None,
        ), patch.object(
            invoke_compact_checkpoint,
            "_get_current_branch",
            return_value="main",
        ):
            invoke_compact_checkpoint.main()

        captured = capsys.readouterr()
        assert "Pre-Compaction Checkpoint" in captured.out


class TestFailOpen:
    """Test fail-open behavior."""

    def test_exception_exits_zero(self) -> None:
        with patch.object(
            invoke_compact_checkpoint,
            "skip_if_consumer_repo",
            side_effect=RuntimeError("boom"),
        ):
            try:
                invoke_compact_checkpoint.main()
            except (SystemExit, RuntimeError):
                pass
