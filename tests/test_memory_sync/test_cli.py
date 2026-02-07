"""Tests for CLI argument parsing and subcommands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.memory_sync.cli import (
    EXIT_INVALID_ARGS,
    EXIT_SUCCESS,
    _read_queue,
    _write_queue,
    main,
)
from scripts.memory_sync.models import SyncOperation


class TestMainEntryPoint:
    """Test CLI entry point."""

    def test_no_args_shows_help(self) -> None:
        """No arguments returns INVALID_ARGS."""
        result = main([])
        assert result == EXIT_INVALID_ARGS

    def test_unknown_command(self) -> None:
        """Unknown command raises SystemExit."""
        with pytest.raises(SystemExit):
            main(["nonexistent"])


class TestValidateCommand:
    """Test the validate subcommand."""

    def test_validate_text_output(
        self, project_root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Validate produces text output."""
        with patch(
            "scripts.memory_sync.cli._find_project_root",
            return_value=project_root,
        ):
            result = main(["validate"])
        assert result == EXIT_SUCCESS
        captured = capsys.readouterr()
        assert "Memory Freshness Report" in captured.out

    def test_validate_json_output(
        self, project_root: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Validate --json produces valid JSON."""
        with patch(
            "scripts.memory_sync.cli._find_project_root",
            return_value=project_root,
        ):
            result = main(["validate", "--json"])
        assert result == EXIT_SUCCESS
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total" in data
        assert "in_sync" in data
        assert "stale" in data
        assert "missing" in data
        assert "orphaned" in data

    def test_validate_with_memories(
        self,
        project_root: Path,
        sample_memory_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Validate reports missing memories."""
        with patch(
            "scripts.memory_sync.cli._find_project_root",
            return_value=project_root,
        ):
            result = main(["validate", "--json"])
        assert result == EXIT_SUCCESS
        data = json.loads(capsys.readouterr().out)
        assert data["missing"] == 1


class TestSyncCommand:
    """Test the sync subcommand."""

    def test_sync_file_not_found(self, project_root: Path) -> None:
        """Sync with nonexistent file returns INVALID_ARGS."""
        with patch(
            "scripts.memory_sync.cli._find_project_root",
            return_value=project_root,
        ):
            result = main(["sync", ".serena/memories/nonexistent.md"])
        assert result == EXIT_INVALID_ARGS

    def test_sync_forgetful_unavailable(
        self, project_root: Path, sample_memory_file: Path
    ) -> None:
        """Sync when Forgetful unavailable returns INVALID_ARGS."""
        with (
            patch(
                "scripts.memory_sync.cli._find_project_root",
                return_value=project_root,
            ),
            patch(
                "scripts.memory_sync.cli.McpClient.is_available",
                return_value=False,
            ),
        ):
            result = main(["sync", ".serena/memories/test-memory.md"])
        assert result == EXIT_INVALID_ARGS


class TestSyncBatchCommand:
    """Test the sync-batch subcommand."""

    def test_batch_no_source(self, project_root: Path) -> None:
        """Batch without --staged or --from-queue returns INVALID_ARGS."""
        with patch(
            "scripts.memory_sync.cli._find_project_root",
            return_value=project_root,
        ):
            result = main(["sync-batch"])
        assert result == EXIT_INVALID_ARGS

    def test_batch_staged_no_changes(self, project_root: Path) -> None:
        """Batch --staged with no memory changes returns SUCCESS."""
        with (
            patch(
                "scripts.memory_sync.cli._find_project_root",
                return_value=project_root,
            ),
            patch(
                "scripts.memory_sync.cli.McpClient.is_available",
                return_value=True,
            ),
            patch(
                "scripts.memory_sync.cli._get_staged_files",
                return_value=["A\tsrc/main.py"],
            ),
        ):
            result = main(["sync-batch", "--staged"])
        assert result == EXIT_SUCCESS

    def test_batch_forgetful_unavailable(self, project_root: Path) -> None:
        """Batch when Forgetful unavailable returns INVALID_ARGS."""
        with (
            patch(
                "scripts.memory_sync.cli._find_project_root",
                return_value=project_root,
            ),
            patch(
                "scripts.memory_sync.cli.McpClient.is_available",
                return_value=False,
            ),
        ):
            result = main(["sync-batch", "--staged"])
        assert result == EXIT_INVALID_ARGS


class TestHookCommand:
    """Test the hook subcommand."""

    def test_hook_no_changes(self, project_root: Path) -> None:
        """Hook with no memory changes returns SUCCESS."""
        with (
            patch(
                "scripts.memory_sync.cli._find_project_root",
                return_value=project_root,
            ),
            patch(
                "scripts.memory_sync.cli._get_staged_files",
                return_value=[],
            ),
        ):
            result = main(["hook"])
        assert result == EXIT_SUCCESS

    def test_hook_queues_changes(self, project_root: Path) -> None:
        """Hook queues changes when Forgetful unavailable."""
        with (
            patch(
                "scripts.memory_sync.cli._find_project_root",
                return_value=project_root,
            ),
            patch(
                "scripts.memory_sync.cli._get_staged_files",
                return_value=["A\t.serena/memories/test.md"],
            ),
            patch(
                "scripts.memory_sync.cli.McpClient.is_available",
                return_value=False,
            ),
        ):
            result = main(["hook"])
        assert result == EXIT_SUCCESS
        queue_path = project_root / ".memory_sync_queue.json"
        assert queue_path.exists()
        data = json.loads(queue_path.read_text())
        assert len(data) == 1
        assert data[0]["path"] == ".serena/memories/test.md"

    def test_hook_never_fails(self, project_root: Path) -> None:
        """Hook always returns 0 even on errors."""
        with (
            patch(
                "scripts.memory_sync.cli._find_project_root",
                return_value=project_root,
            ),
            patch(
                "scripts.memory_sync.cli._get_staged_files",
                return_value=["A\t.serena/memories/test.md"],
            ),
            patch(
                "scripts.memory_sync.cli.McpClient.is_available",
                return_value=True,
            ),
            patch(
                "scripts.memory_sync.cli.McpClient.create",
                side_effect=Exception("MCP boom"),
            ),
        ):
            # The hook catches exceptions internally
            result = main(["hook", "--immediate"])
        # Hook always returns 0
        assert result == EXIT_SUCCESS


class TestQueueOperations:
    """Test queue file read/write."""

    def test_write_and_read_queue(self, project_root: Path) -> None:
        """Round-trip queue write and read."""
        changes = [
            (Path(".serena/memories/a.md"), SyncOperation.CREATE),
            (Path(".serena/memories/b.md"), SyncOperation.UPDATE),
        ]
        _write_queue(project_root, changes)
        loaded = _read_queue(project_root)
        assert len(loaded) == 2
        assert loaded[0] == (Path(".serena/memories/a.md"), SyncOperation.CREATE)
        assert loaded[1] == (Path(".serena/memories/b.md"), SyncOperation.UPDATE)

    def test_read_empty_queue(self, project_root: Path) -> None:
        """Reading nonexistent queue returns empty list."""
        loaded = _read_queue(project_root)
        assert loaded == []

    def test_read_corrupt_queue(self, project_root: Path) -> None:
        """Reading corrupt queue returns empty list."""
        queue_path = project_root / ".memory_sync_queue.json"
        queue_path.write_text("not json", encoding="utf-8")
        loaded = _read_queue(project_root)
        assert loaded == []
