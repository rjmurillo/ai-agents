"""Tests for freshness validation."""

from __future__ import annotations

from pathlib import Path

from scripts.memory_sync.freshness import check_freshness
from scripts.memory_sync.models import FreshnessStatus
from scripts.memory_sync.sync_engine import compute_content_hash, save_state


class TestCheckFreshness:
    """Test freshness report generation."""

    def test_empty_dir(self, project_root: Path) -> None:
        """Empty memories dir produces zero-count report."""
        report = check_freshness(project_root)
        assert report.total == 0
        assert report.in_sync == 0
        assert report.stale == 0
        assert report.missing == 0
        assert report.orphaned == 0

    def test_missing_memory(
        self, project_root: Path, sample_memory_file: Path
    ) -> None:
        """Memory file without state is MISSING."""
        report = check_freshness(project_root)
        assert report.total == 1
        assert report.missing == 1
        detail = report.details[0]
        assert detail.name == "test-memory"
        assert detail.status == FreshnessStatus.MISSING

    def test_in_sync_memory(
        self, project_root: Path, sample_memory_file: Path
    ) -> None:
        """Memory file matching state hash is IN_SYNC."""
        content = sample_memory_file.read_text("utf-8")
        content_hash = compute_content_hash(content)
        save_state(project_root, {
            "test-memory": {"forgetful_id": "42", "hash": content_hash},
        })

        report = check_freshness(project_root)
        assert report.total == 1
        assert report.in_sync == 1
        assert report.details[0].status == FreshnessStatus.IN_SYNC
        assert report.details[0].forgetful_id == "42"

    def test_stale_memory(
        self, project_root: Path, sample_memory_file: Path
    ) -> None:
        """Memory file with different hash is STALE."""
        save_state(project_root, {
            "test-memory": {"forgetful_id": "42", "hash": "old-hash"},
        })

        report = check_freshness(project_root)
        assert report.total == 1
        assert report.stale == 1
        assert report.details[0].status == FreshnessStatus.STALE

    def test_orphaned_entry(self, project_root: Path) -> None:
        """State entry without Serena file is ORPHANED."""
        save_state(project_root, {
            "deleted-memory": {"forgetful_id": "99", "hash": "xyz"},
        })

        report = check_freshness(project_root)
        orphaned = [d for d in report.details if d.status == FreshnessStatus.ORPHANED]
        assert len(orphaned) == 1
        assert orphaned[0].name == "deleted-memory"
        assert report.orphaned == 1

    def test_mixed_statuses(self, project_root: Path) -> None:
        """Report with multiple status types."""
        memories_dir = project_root / ".serena" / "memories"

        # In-sync memory
        synced = memories_dir / "synced.md"
        synced.write_text("---\nid: synced\n---\nSynced content\n", encoding="utf-8")
        synced_hash = compute_content_hash(synced.read_text("utf-8"))

        # Stale memory
        stale = memories_dir / "stale.md"
        stale.write_text("---\nid: stale\n---\nNew content\n", encoding="utf-8")

        # Missing memory (no state entry)
        missing = memories_dir / "missing.md"
        missing.write_text("---\nid: missing\n---\nNew file\n", encoding="utf-8")

        save_state(project_root, {
            "synced": {"forgetful_id": "1", "hash": synced_hash},
            "stale": {"forgetful_id": "2", "hash": "old-hash"},
            "orphaned": {"forgetful_id": "3", "hash": "dead"},
        })

        report = check_freshness(project_root)
        assert report.in_sync == 1
        assert report.stale == 1
        assert report.missing == 1
        assert report.orphaned == 1
        assert report.total == 4

    def test_custom_memories_dir(self, tmp_path: Path) -> None:
        """Support custom memories directory."""
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        (custom_dir / "test.md").write_text("---\nid: test\n---\nContent\n")
        project_root = tmp_path
        (project_root / ".git").mkdir()

        report = check_freshness(project_root, memories_dir=custom_dir)
        assert report.total == 1
        assert report.missing == 1

    def test_duration_is_recorded(self, project_root: Path) -> None:
        """Report includes duration in milliseconds."""
        report = check_freshness(project_root)
        assert report.duration_ms >= 0
