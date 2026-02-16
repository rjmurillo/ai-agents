"""Tests for scripts.forgetful.export_forgetful_memories module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.forgetful.export_forgetful_memories import (
    TABLE_MAPPING,
    export_table,
    run_sqlite3,
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


class TestRunSqlite3:
    def _make_result(
        self, returncode: int = 0, stdout: str = "", stderr: str = "",
    ) -> object:
        return type(
            "R", (), {"returncode": returncode, "stderr": stderr, "stdout": stdout},
        )()

    def test_logs_stderr_on_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock = self._make_result(1, stderr="database is locked\n")
        with patch("subprocess.run", return_value=mock):
            result = run_sqlite3("/fake/db", "SELECT 1")
        assert result is None
        assert "database is locked" in capsys.readouterr().err

    def test_no_warning_on_empty_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("subprocess.run", return_value=self._make_result(1)):
            result = run_sqlite3("/fake/db", "SELECT 1")
        assert result is None
        assert capsys.readouterr().err == ""

    def test_returns_stdout_on_success(self) -> None:
        with patch("subprocess.run", return_value=self._make_result(0, stdout="hello")):
            result = run_sqlite3("/fake/db", "SELECT 1")
        assert result == "hello"


class TestExportTable:
    def test_logs_json_parse_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """export_table logs JSONDecodeError details to stderr."""
        # Mock get_table_columns to return columns, run_sqlite3 to return bad JSON
        with (
            patch(
                "scripts.forgetful.export_forgetful_memories.get_table_columns",
                return_value=["id", "name"],
            ),
            patch(
                "scripts.forgetful.export_forgetful_memories.run_sqlite3",
                return_value="not valid json{{{",
            ),
        ):
            result = export_table("/fake/db", "memories")
        assert result == []
        err = capsys.readouterr().err
        assert "Failed to parse JSON for table 'memories'" in err
