"""Tests for scripts.forgetful.export_forgetful_memories module."""

from __future__ import annotations

import os
from pathlib import Path

from scripts.forgetful.export_forgetful_memories import (
    TABLE_MAPPING,
    validate_output_path,
)


class TestValidateOutputPath:
    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()
        output = exports_dir / "backup.json"
        assert validate_output_path(output, exports_dir) is True

    def test_rejects_traversal(self, tmp_path: Path) -> None:
        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()
        output = tmp_path / "outside.json"
        assert validate_output_path(output, exports_dir) is False

    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()
        output = exports_dir / ".." / "escape.json"
        assert validate_output_path(output, exports_dir) is False


class TestTableMapping:
    def test_all_groups_have_tables(self) -> None:
        for group, tables in TABLE_MAPPING.items():
            assert len(tables) > 0, f"Group {group} has no tables"

    def test_memories_group_includes_memory_links(self) -> None:
        assert "memory_links" in TABLE_MAPPING["memories"]

    def test_associations_group(self) -> None:
        assoc = TABLE_MAPPING["associations"]
        assert all("association" in t for t in assoc)
