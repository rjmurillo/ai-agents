"""Tests for the .claude-mem/scripts/ memory EXPORT scripts.

Importer resolution and exit codes live in
tests/claude_mem/test_importer_resolution.py. This module must not load the
importer: both modules register into sys.modules under the same key, so a load
here would overwrite the one the importer tests rely on.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

# Import modules under test by file path since they live outside scripts/

_base = os.path.join(os.path.dirname(__file__), "..", ".claude-mem", "scripts")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_base, filename))
    assert spec is not None, f"Failed to find {filename}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, f"Module spec for {filename} has no loader"
    # dataclasses resolves a class's module through sys.modules, so a module
    # executed without registration raises AttributeError at class creation.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_export_direct = _load("export_claude_mem_direct", "export_claude_mem_direct.py")
_export_memories = _load("export_claude_mem_memories", "export_claude_mem_memories.py")
_export_backup = _load("export_claude_mem_full_backup", "export_claude_mem_full_backup.py")


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
    @pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 binary not installed")
    def test_returns_negative_on_error(self, tmp_path: Path) -> None:
        # A directory is unopenable as a database, so the CLI fails at open in
        # every sqlite3 version. A nonexistent file path does not error here:
        # the shell creates the database lazily and "SELECT 1;" touches no
        # table, so sqlite3 exits 0 and get_count returns 1.
        result = _export_direct.get_count(str(tmp_path), "SELECT 1;")
        assert result == -1

    @pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 binary not installed")
    def test_returns_negative_on_non_numeric_output(self, tmp_path: Path) -> None:
        db = tmp_path / "real.db"
        result = _export_direct.get_count(str(db), "SELECT 'not-a-number';")
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


class TestSecurityReviewBoundary:
    @pytest.mark.parametrize(
        ("module", "runner_name"),
        [
            (_export_direct, "_run_security_review_direct"),
            (_export_memories, "_run_security_review_memories"),
            (_export_backup, "_run_security_review"),
        ],
        ids=["direct", "memories", "full-backup"],
    )
    def test_passes_export_path_positionally(
        self,
        module: object,
        runner_name: str,
        tmp_path: Path,
    ) -> None:
        export_file = tmp_path / "memory export.json"
        export_file.write_text('{"data": "safe content"}', encoding="utf-8")

        runner = getattr(module, runner_name)

        assert runner(export_file) == 0


class TestExportDirectMain:
    def test_exits_1_when_sqlite3_missing(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = _export_direct.main(["--project", "test"])
        assert result == 1


class TestExportMemoriesMain:
    def test_exits_1_with_invalid_query(self) -> None:
        result = _export_memories.main(["query with $pecial; chars"])
        assert result == 1
