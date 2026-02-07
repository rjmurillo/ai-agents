"""Tests for sync engine logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from scripts.memory_sync.models import SyncOperation
from scripts.memory_sync.sync_engine import (
    build_create_payload,
    build_update_payload,
    compute_content_hash,
    detect_changes,
    load_state,
    save_state,
    sync_batch,
    sync_memory,
)


class TestComputeContentHash:
    """Test content hashing."""

    def test_deterministic(self) -> None:
        """Same input produces same hash."""
        h1 = compute_content_hash("hello world")
        h2 = compute_content_hash("hello world")
        assert h1 == h2

    def test_different_content_different_hash(self) -> None:
        """Different input produces different hash."""
        h1 = compute_content_hash("hello")
        h2 = compute_content_hash("world")
        assert h1 != h2

    def test_sha256_format(self) -> None:
        """Hash is a 64-char hex string (SHA-256)."""
        h = compute_content_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestDetectChanges:
    """Test git staged file parsing."""

    def test_added_memory(self) -> None:
        """Detect an added memory file."""
        lines = ["A\t.serena/memories/test.md"]
        changes = detect_changes(lines)
        assert len(changes) == 1
        assert changes[0] == (Path(".serena/memories/test.md"), SyncOperation.CREATE)

    def test_modified_memory(self) -> None:
        """Detect a modified memory file."""
        lines = ["M\t.serena/memories/test.md"]
        changes = detect_changes(lines)
        assert len(changes) == 1
        assert changes[0][1] == SyncOperation.UPDATE

    def test_deleted_memory(self) -> None:
        """Detect a deleted memory file."""
        lines = ["D\t.serena/memories/test.md"]
        changes = detect_changes(lines)
        assert len(changes) == 1
        assert changes[0][1] == SyncOperation.DELETE

    def test_renamed_memory(self) -> None:
        """Renamed files map to UPDATE."""
        lines = ["R100\t.serena/memories/old.md\t.serena/memories/new.md"]
        changes = detect_changes(lines)
        # The first tab-separated field after status is the path
        assert len(changes) == 1
        assert changes[0][1] == SyncOperation.UPDATE

    def test_non_memory_files_ignored(self) -> None:
        """Non-memory files are skipped."""
        lines = [
            "A\tsrc/main.py",
            "M\t.agents/sessions/session.json",
            "A\t.serena/memories/real.md",
        ]
        changes = detect_changes(lines)
        assert len(changes) == 1
        assert changes[0][0] == Path(".serena/memories/real.md")

    def test_empty_lines_skipped(self) -> None:
        """Empty lines don't cause errors."""
        lines = ["", "A\t.serena/memories/test.md", ""]
        changes = detect_changes(lines)
        assert len(changes) == 1

    def test_unknown_status_ignored(self) -> None:
        """Unknown git status is ignored."""
        lines = ["X\t.serena/memories/test.md"]
        changes = detect_changes(lines)
        assert len(changes) == 0


class TestStateManagement:
    """Test sync state file operations."""

    def test_load_empty_state(self, project_root: Path) -> None:
        """Loading from nonexistent file returns empty dict."""
        state = load_state(project_root)
        assert state == {}

    def test_save_and_load(self, project_root: Path) -> None:
        """Round-trip save and load."""
        state = {"test-memory": {"forgetful_id": "42", "hash": "abc123"}}
        save_state(project_root, state)
        loaded = load_state(project_root)
        assert loaded == state

    def test_overwrite_state(self, project_root: Path) -> None:
        """Saving overwrites existing state."""
        save_state(project_root, {"old": {}})
        save_state(project_root, {"new": {}})
        loaded = load_state(project_root)
        assert "new" in loaded
        assert "old" not in loaded


class TestBuildPayloads:
    """Test payload construction."""

    def _make_memory(
        self,
        memory_id: str = "test",
        content: str = "Test content",
        tags: list[str] | None = None,
        confidence: float = 0.8,
    ) -> MagicMock:
        memory = MagicMock()
        memory.id = memory_id
        memory.content = content
        memory.tags = ["testing"] if tags is None else tags
        memory.confidence = confidence
        return memory

    def test_create_payload_fields(self) -> None:
        """Create payload has all required fields."""
        memory = self._make_memory()
        payload = build_create_payload(memory, Path(".serena/memories/test.md"))
        assert payload["title"] == "test"
        assert payload["content"] == "Test content"
        assert payload["context"] == "Synced from Serena: .serena/memories/test.md"
        assert payload["keywords"] == ["testing"]
        assert payload["tags"] == ["testing"]
        assert payload["importance"] == 8
        assert payload["source_repo"] == "rjmurillo/ai-agents"
        assert payload["source_files"] == [".serena/memories/test.md"]
        assert payload["encoding_agent"] == "memory-sync/0.1.0"
        assert payload["confidence"] == 0.8

    def test_create_payload_default_keywords(self) -> None:
        """Uses filename stem when tags are empty."""
        memory = self._make_memory(tags=[])
        payload = build_create_payload(memory, Path(".serena/memories/my-memory.md"))
        assert payload["keywords"] == ["my-memory"]

    def test_update_payload_includes_id(self) -> None:
        """Update payload includes memory_id."""
        memory = self._make_memory()
        payload = build_update_payload(
            memory, Path(".serena/memories/test.md"), "42"
        )
        assert payload["memory_id"] == 42

    def test_confidence_to_importance_clamping(self) -> None:
        """Importance is clamped between 1 and 10."""
        low = self._make_memory(confidence=0.0)
        high = self._make_memory(confidence=1.5)
        assert build_create_payload(low, Path("x.md"))["importance"] == 1
        assert build_create_payload(high, Path("x.md"))["importance"] == 10


class TestSyncMemory:
    """Test single memory sync operations."""

    def test_skip_operation(
        self, mock_mcp_client: MagicMock, project_root: Path
    ) -> None:
        """SKIP operation returns success immediately."""
        result = sync_memory(
            mock_mcp_client,
            Path(".serena/memories/test.md"),
            SyncOperation.SKIP,
            project_root,
        )
        assert result.success
        assert result.operation == SyncOperation.SKIP

    def test_create_operation(
        self,
        mock_mcp_client: MagicMock,
        project_root: Path,
        sample_memory_file: Path,
    ) -> None:
        """CREATE parses file and calls create_memory."""
        result = sync_memory(
            mock_mcp_client,
            Path(".serena/memories/test-memory.md"),
            SyncOperation.CREATE,
            project_root,
        )
        assert result.success
        assert result.operation == SyncOperation.CREATE
        mock_mcp_client.call_tool.assert_called_once()

    def test_create_parse_error(
        self, mock_mcp_client: MagicMock, project_root: Path
    ) -> None:
        """CREATE with missing file returns parse error."""
        result = sync_memory(
            mock_mcp_client,
            Path(".serena/memories/nonexistent.md"),
            SyncOperation.CREATE,
            project_root,
        )
        assert not result.success
        assert "Parse error" in (result.error or "")

    def test_dry_run_no_mcp_calls(
        self,
        mock_mcp_client: MagicMock,
        project_root: Path,
        sample_memory_file: Path,
    ) -> None:
        """Dry run doesn't call MCP."""
        result = sync_memory(
            mock_mcp_client,
            Path(".serena/memories/test-memory.md"),
            SyncOperation.CREATE,
            project_root,
            dry_run=True,
        )
        assert result.success
        mock_mcp_client.call_tool.assert_not_called()

    def test_update_skips_unchanged(
        self,
        mock_mcp_client: MagicMock,
        project_root: Path,
        sample_memory_file: Path,
    ) -> None:
        """UPDATE with unchanged content skips sync."""
        content = sample_memory_file.read_text("utf-8")
        content_hash = compute_content_hash(content)
        save_state(project_root, {
            "test-memory": {"forgetful_id": "42", "hash": content_hash},
        })

        result = sync_memory(
            mock_mcp_client,
            Path(".serena/memories/test-memory.md"),
            SyncOperation.UPDATE,
            project_root,
        )
        assert result.success
        assert result.operation == SyncOperation.SKIP
        mock_mcp_client.call_tool.assert_not_called()

    def test_update_force_ignores_hash(
        self,
        mock_mcp_client: MagicMock,
        project_root: Path,
        sample_memory_file: Path,
    ) -> None:
        """UPDATE with --force syncs even if hash matches."""
        content = sample_memory_file.read_text("utf-8")
        content_hash = compute_content_hash(content)
        save_state(project_root, {
            "test-memory": {"forgetful_id": "42", "hash": content_hash},
        })

        result = sync_memory(
            mock_mcp_client,
            Path(".serena/memories/test-memory.md"),
            SyncOperation.UPDATE,
            project_root,
            force=True,
        )
        assert result.success
        mock_mcp_client.call_tool.assert_called_once()

    def test_delete_with_state(
        self, mock_mcp_client: MagicMock, project_root: Path
    ) -> None:
        """DELETE with existing state calls mark_memory_obsolete."""
        save_state(project_root, {
            "test-memory": {"forgetful_id": "42", "hash": "abc"},
        })
        result = sync_memory(
            mock_mcp_client,
            Path(".serena/memories/test-memory.md"),
            SyncOperation.DELETE,
            project_root,
        )
        assert result.success
        assert result.operation == SyncOperation.DELETE
        mock_mcp_client.call_tool.assert_called_once_with(
            "mark_memory_obsolete",
            {"memory_id": 42, "reason": "Deleted from Serena: .serena/memories/test-memory.md"},
        )

    def test_delete_without_state(
        self, mock_mcp_client: MagicMock, project_root: Path
    ) -> None:
        """DELETE without state skips MCP call."""
        result = sync_memory(
            mock_mcp_client,
            Path(".serena/memories/test-memory.md"),
            SyncOperation.DELETE,
            project_root,
        )
        assert result.success
        assert result.operation == SyncOperation.SKIP
        mock_mcp_client.call_tool.assert_not_called()


class TestSyncBatch:
    """Test batch sync operations."""

    def test_empty_batch(
        self, mock_mcp_client: MagicMock, project_root: Path
    ) -> None:
        """Empty batch returns empty results."""
        results = sync_batch(mock_mcp_client, [], project_root)
        assert results == []

    def test_batch_processes_all(
        self,
        mock_mcp_client: MagicMock,
        project_root: Path,
        sample_memory_file: Path,
    ) -> None:
        """Batch processes all changes."""
        changes = [
            (Path(".serena/memories/test-memory.md"), SyncOperation.CREATE),
        ]
        results = sync_batch(mock_mcp_client, changes, project_root)
        assert len(results) == 1
        assert results[0].success
