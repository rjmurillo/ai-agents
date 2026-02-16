"""Tests for error handling in import_forgetful_memories.

Validates that:
- json.JSONDecodeError produces specific error message with parse details
- KeyError produces specific error message with the missing key name
- RuntimeError from import_table is caught and reported per file
- Other exceptions propagate instead of being silently swallowed
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "scripts" / "forgetful"
)
sys.path.insert(0, SCRIPTS_DIR)

from import_forgetful_memories import main  # noqa: E402


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a fake database file."""
    db = tmp_path / "forgetful.db"
    db.write_text("")
    return db


@pytest.fixture
def valid_export() -> dict:
    """Return a minimal valid export structure."""
    return {
        "export_metadata": {"version": "1.0"},
        "data": {
            "memories": [{"id": 1, "title": "test", "content": "hello"}],
        },
    }


class TestJsonDecodeError:
    """json.JSONDecodeError produces a specific, actionable message."""

    def test_invalid_json_reports_parse_error(
        self, tmp_path: Path, db_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json", encoding="utf-8")

        result = main([
            "--input-files", str(bad_file),
            "--database-path", str(db_path),
            "--force",
        ])

        assert result == 1
        captured = capsys.readouterr()
        assert "WARNING: Failed to parse bad.json" in captured.out
        assert "Invalid JSON" in captured.out

    def test_truncated_json_reports_parse_error(
        self, tmp_path: Path, db_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad_file = tmp_path / "truncated.json"
        bad_file.write_text('{"export_metadata": {"ver', encoding="utf-8")

        result = main([
            "--input-files", str(bad_file),
            "--database-path", str(db_path),
            "--force",
        ])

        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid JSON" in captured.out

    def test_json_error_includes_file_name_in_failure_list(
        self, tmp_path: Path, db_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad_file = tmp_path / "corrupt.json"
        bad_file.write_text("<<<not json>>>", encoding="utf-8")

        result = main([
            "--input-files", str(bad_file),
            "--database-path", str(db_path),
            "--force",
        ])

        assert result == 1
        captured = capsys.readouterr()
        assert "FAIL corrupt.json: Invalid JSON:" in captured.out


class TestKeyError:
    """KeyError produces a message with the missing key name."""

    def test_missing_key_reports_specific_key(
        self,
        tmp_path: Path,
        db_path: Path,
        valid_export: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        export_file = tmp_path / "export.json"
        export_file.write_text(json.dumps(valid_export), encoding="utf-8")

        def fake_get_schema(_db: str, _table: str) -> list[str]:
            return ["id", "title", "content"]

        def fake_import_table(
            _db: str, _table: str, _rows: list, _cols: list, _mode: str
        ) -> tuple[int, int, int]:
            raise KeyError("missing_field")

        with (
            patch(
                "import_forgetful_memories.get_schema_columns",
                side_effect=fake_get_schema,
            ),
            patch(
                "import_forgetful_memories.import_table",
                side_effect=fake_import_table,
            ),
        ):
            result = main([
                "--input-files", str(export_file),
                "--database-path", str(db_path),
                "--force",
            ])

        assert result == 1
        captured = capsys.readouterr()
        assert "Missing key" in captured.out
        assert "'missing_field'" in captured.out

    def test_key_error_includes_file_name(
        self,
        tmp_path: Path,
        db_path: Path,
        valid_export: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        export_file = tmp_path / "data.json"
        export_file.write_text(json.dumps(valid_export), encoding="utf-8")

        def fake_get_schema(_db: str, _table: str) -> list[str]:
            return ["id", "title", "content"]

        def fake_import_table(
            _db: str, _table: str, _rows: list, _cols: list, _mode: str
        ) -> tuple[int, int, int]:
            raise KeyError("bad_key")

        with (
            patch(
                "import_forgetful_memories.get_schema_columns",
                side_effect=fake_get_schema,
            ),
            patch(
                "import_forgetful_memories.import_table",
                side_effect=fake_import_table,
            ),
        ):
            result = main([
                "--input-files", str(export_file),
                "--database-path", str(db_path),
                "--force",
            ])

        assert result == 1
        captured = capsys.readouterr()
        assert "FAIL data.json: Missing key:" in captured.out


class TestRuntimeError:
    """RuntimeError from import_table is caught per file."""

    def test_runtime_error_reports_per_file(
        self,
        tmp_path: Path,
        db_path: Path,
        valid_export: dict,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        export_file = tmp_path / "export.json"
        export_file.write_text(json.dumps(valid_export), encoding="utf-8")

        def fake_get_schema(_db: str, _table: str) -> list[str]:
            return ["id", "title", "content"]

        def fake_import_table(
            _db: str, _table: str, _rows: list, _cols: list, _mode: str
        ) -> tuple[int, int, int]:
            raise RuntimeError("Duplicate record in memories (fail mode)")

        with (
            patch(
                "import_forgetful_memories.get_schema_columns",
                side_effect=fake_get_schema,
            ),
            patch(
                "import_forgetful_memories.import_table",
                side_effect=fake_import_table,
            ),
        ):
            result = main([
                "--input-files", str(export_file),
                "--database-path", str(db_path),
                "--force",
            ])

        assert result == 1
        captured = capsys.readouterr()
        assert "WARNING: Import failed for export.json" in captured.out
        assert "Duplicate record" in captured.out


class TestUnexpectedExceptionPropagates:
    """Unexpected exceptions are not silently swallowed."""

    def test_type_error_propagates(
        self,
        tmp_path: Path,
        db_path: Path,
        valid_export: dict,
    ) -> None:
        export_file = tmp_path / "export.json"
        export_file.write_text(json.dumps(valid_export), encoding="utf-8")

        def fake_get_schema(_db: str, _table: str) -> list[str]:
            return ["id", "title", "content"]

        def fake_import_table(
            _db: str, _table: str, _rows: list, _cols: list, _mode: str
        ) -> tuple[int, int, int]:
            raise TypeError("unexpected programming error")

        with (
            patch(
                "import_forgetful_memories.get_schema_columns",
                side_effect=fake_get_schema,
            ),
            patch(
                "import_forgetful_memories.import_table",
                side_effect=fake_import_table,
            ),
            pytest.raises(TypeError, match="unexpected programming error"),
        ):
            main([
                "--input-files", str(export_file),
                "--database-path", str(db_path),
                "--force",
            ])

    def test_os_error_propagates(
        self,
        tmp_path: Path,
        db_path: Path,
        valid_export: dict,
    ) -> None:
        export_file = tmp_path / "export.json"
        export_file.write_text(json.dumps(valid_export), encoding="utf-8")

        def fake_get_schema(_db: str, _table: str) -> list[str]:
            raise OSError("disk failure")

        with (
            patch(
                "import_forgetful_memories.get_schema_columns",
                side_effect=fake_get_schema,
            ),
            pytest.raises(OSError, match="disk failure"),
        ):
            main([
                "--input-files", str(export_file),
                "--database-path", str(db_path),
                "--force",
            ])
