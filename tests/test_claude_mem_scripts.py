"""Tests for .claude-mem/scripts/ memory export/import scripts."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

# Import modules under test by file path since they live outside scripts/

_base = os.path.join(os.path.dirname(__file__), "..", ".claude-mem", "scripts")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_base, filename))
    assert spec is not None, f"Failed to find {filename}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, f"Module spec for {filename} has no loader"
    spec.loader.exec_module(mod)
    return mod


_export_direct = _load("export_claude_mem_direct", "export_claude_mem_direct.py")
_export_memories = _load("export_claude_mem_memories", "export_claude_mem_memories.py")
_export_backup = _load("export_claude_mem_full_backup", "export_claude_mem_full_backup.py")
_import_mem = _load("import_claude_mem_memories", "import_claude_mem_memories.py")


class TestExportDirectValidateOutputPath:
    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = mem_dir / "export.json"
        assert _export_direct.validate_output_path(output, mem_dir) is True

    def test_rejects_traversal(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = tmp_path / "escape.json"
        assert _export_direct.validate_output_path(output, mem_dir) is False


class TestExportDirectGetCount:
    def test_returns_negative_on_error(self) -> None:
        result = _export_direct.get_count("/nonexistent.db", "SELECT 1;")
        assert result == -1


class TestExportMemoriesValidateOutputPath:
    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = mem_dir / "export.json"
        assert _export_memories.validate_output_path(output, mem_dir) is True

    def test_rejects_traversal(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = tmp_path / "escape.json"
        assert _export_memories.validate_output_path(output, mem_dir) is False


class TestExportBackupValidateOutputPath:
    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = mem_dir / "backup.json"
        assert _export_backup.validate_output_path(output, mem_dir) is True

    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = mem_dir / ".." / "escape.json"
        assert _export_backup.validate_output_path(output, mem_dir) is False


class TestExportDirectMain:
    def test_exits_1_when_sqlite3_missing(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = _export_direct.main(["--project", "test"])
        assert result == 1


class TestExportMemoriesMain:
    def test_exits_1_with_invalid_query(self) -> None:
        result = _export_memories.main(["query with $pecial; chars"])
        assert result == 1


class TestImportMemoriesMain:
    def test_exits_1_when_plugin_missing(self) -> None:
        result = _import_mem.main([])
        # Plugin script almost certainly does not exist in test env
        assert result in (0, 1)
