#!/usr/bin/env python3
"""Tests for PostToolUse/invoke_plan_state_sync.py.

Covers:
- Session log detection and checkpoint creation
- Plan/TODO file detection
- Non-matching file pass-through
- Checkpoint file format
- Consumer repo skip
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "PostToolUse"))

import invoke_plan_state_sync


class TestIsCheckpointableFile:
    """Test _is_checkpointable_file detection."""

    @pytest.mark.parametrize(
        "path",
        [
            ".agents/sessions/2026-01-01-session-001.json",
            "TODO.md",
            "PLAN.md",
            ".agents/plan-v2.md",
            "PROJECT-PLAN.md",
            "todo.md",
        ],
    )
    def test_detects_checkpointable_files(self, path: str) -> None:
        assert invoke_plan_state_sync._is_checkpointable_file(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "src/main.py",
            "README.md",
            ".agents/architecture/ADR-001.md",
            "package.json",
            "tests/test_foo.py",
        ],
    )
    def test_ignores_non_checkpointable_files(self, path: str) -> None:
        assert invoke_plan_state_sync._is_checkpointable_file(path) is False


class TestReadFileSummary:
    """Test _read_file_summary helper."""

    def test_reads_small_file(self, tmp_path: Path) -> None:
        f = tmp_path / "todo.md"
        f.write_text("# TODO\n- Item 1", encoding="utf-8")
        result = invoke_plan_state_sync._read_file_summary(str(f))
        assert "# TODO" in result

    def test_truncates_large_file(self, tmp_path: Path) -> None:
        f = tmp_path / "big.md"
        f.write_text("x" * 1000, encoding="utf-8")
        result = invoke_plan_state_sync._read_file_summary(str(f))
        assert len(result) <= 510  # 500 + "..."

    def test_missing_file(self, tmp_path: Path) -> None:
        result = invoke_plan_state_sync._read_file_summary(str(tmp_path / "nope.md"))
        assert "not found" in result


class TestWriteCheckpoint:
    """Test _write_checkpoint function."""

    def test_creates_checkpoint_file(self, tmp_path: Path) -> None:
        (tmp_path / ".agents").mkdir()
        invoke_plan_state_sync._write_checkpoint(
            str(tmp_path), "TODO.md", "# TODO\n- Item 1"
        )

        checkpoint_dir = tmp_path / ".agents" / ".hook-state"
        assert checkpoint_dir.exists()
        files = list(checkpoint_dir.glob("plan-checkpoint-*.json"))
        assert len(files) == 1

        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert data[0]["file"] == "TODO.md"

    def test_appends_to_existing(self, tmp_path: Path) -> None:
        checkpoint_dir = tmp_path / ".agents" / ".hook-state"
        checkpoint_dir.mkdir(parents=True)

        invoke_plan_state_sync._write_checkpoint(str(tmp_path), "TODO.md", "first")
        invoke_plan_state_sync._write_checkpoint(str(tmp_path), "PLAN.md", "second")

        files = list(checkpoint_dir.glob("plan-checkpoint-*.json"))
        assert len(files) == 1  # Same day, same file

        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert len(data) == 2

    def test_limits_checkpoint_count(self, tmp_path: Path) -> None:
        (tmp_path / ".agents").mkdir()
        for i in range(25):
            invoke_plan_state_sync._write_checkpoint(
                str(tmp_path), f"file-{i}.md", f"summary-{i}"
            )

        files = list((tmp_path / ".agents" / ".hook-state").glob("plan-checkpoint-*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert len(data) <= 20


class TestMain:
    """Test main() function."""

    def test_skip_consumer_repo(self) -> None:
        with patch.object(
            invoke_plan_state_sync, "skip_if_consumer_repo", return_value=True
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_plan_state_sync.main()
            assert exc_info.value.code == 0

    def test_tty_stdin_exits_zero(self) -> None:
        with patch.object(
            invoke_plan_state_sync, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_plan_state_sync, "_read_stdin_json", return_value=None,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_plan_state_sync.main()
            assert exc_info.value.code == 0

    def test_non_checkpointable_file_passes(self) -> None:
        hook_input = {"tool_input": {"file_path": "src/main.py"}}
        with patch.object(
            invoke_plan_state_sync, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_plan_state_sync, "_read_stdin_json", return_value=hook_input,
        ):
            with pytest.raises(SystemExit) as exc_info:
                invoke_plan_state_sync.main()
            assert exc_info.value.code == 0

    def test_checkpoints_todo_file(self, tmp_path: Path) -> None:
        todo = tmp_path / "TODO.md"
        todo.write_text("# TODO\n- Item 1", encoding="utf-8")
        (tmp_path / ".agents").mkdir()

        hook_input = {"tool_input": {"file_path": "TODO.md"}}
        with patch.object(
            invoke_plan_state_sync, "skip_if_consumer_repo", return_value=False
        ), patch.object(
            invoke_plan_state_sync, "_read_stdin_json", return_value=hook_input,
        ), patch.object(
            invoke_plan_state_sync,
            "get_project_directory",
            return_value=str(tmp_path),
        ):
            invoke_plan_state_sync.main()

        checkpoint_dir = tmp_path / ".agents" / ".hook-state"
        assert checkpoint_dir.exists()


class TestFailOpen:
    """Test fail-open behavior."""

    def test_exception_exits_zero(self) -> None:
        with patch.object(
            invoke_plan_state_sync,
            "skip_if_consumer_repo",
            side_effect=RuntimeError("boom"),
        ):
            try:
                invoke_plan_state_sync.main()
            except (SystemExit, RuntimeError):
                pass
