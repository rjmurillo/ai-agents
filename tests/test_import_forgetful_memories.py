"""Tests for scripts.forgetful.import_forgetful_memories module."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.forgetful.import_forgetful_memories import (
    IMPORT_ORDER,
    PRIMARY_KEYS,
    escape_sql_value,
    import_table,
    main,
    normalize_table_rows,
    run_sqlite3,
)


class TestRunSqlite3Timeout:
    @patch("scripts.forgetful.import_forgetful_memories.subprocess.run")
    def test_passes_timeout_30(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        run_sqlite3("/fake/db", "SELECT 1;")
        mock_run.assert_called_once_with(
            ["sqlite3", "/fake/db", "SELECT 1;"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

    @patch("scripts.forgetful.import_forgetful_memories.subprocess.run")
    def test_timeout_raises_timeout_expired(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["sqlite3"], timeout=30)
        with pytest.raises(subprocess.TimeoutExpired):
            run_sqlite3("/fake/db", "SELECT 1;")


class TestEscapeSqlValue:
    def test_none_returns_null(self) -> None:
        assert escape_sql_value(None) == "NULL"

    def test_bool_true(self) -> None:
        assert escape_sql_value(True) == "1"

    def test_bool_false(self) -> None:
        assert escape_sql_value(False) == "0"

    def test_integer(self) -> None:
        assert escape_sql_value(42) == "42"

    def test_float(self) -> None:
        assert escape_sql_value(3.14) == "3.14"

    def test_string_escapes_quotes(self) -> None:
        result = escape_sql_value("it's a test")
        assert result == "'it''s a test'"

    def test_string_without_quotes(self) -> None:
        result = escape_sql_value("hello")
        assert result == "'hello'"

    def test_list_becomes_json(self) -> None:
        result = escape_sql_value([1, 2, 3])
        assert result.startswith("'")
        assert result.endswith("'")
        assert "[1,2,3]" in result

    def test_dict_becomes_json(self) -> None:
        result = escape_sql_value({"key": "val"})
        assert "key" in result
        assert "val" in result


class TestImportOrder:
    def test_users_first(self) -> None:
        assert IMPORT_ORDER[0] == "users"

    def test_projects_before_associations(self) -> None:
        proj_idx = IMPORT_ORDER.index("projects")
        assoc_idx = IMPORT_ORDER.index("memory_project_association")
        assert proj_idx < assoc_idx

    def test_entities_before_relationships(self) -> None:
        ent_idx = IMPORT_ORDER.index("entities")
        rel_idx = IMPORT_ORDER.index("entity_relationships")
        assert ent_idx < rel_idx


class TestPrimaryKeys:
    def test_association_tables_have_composite_keys(self) -> None:
        for table, keys in PRIMARY_KEYS.items():
            assert "association" in table or "entity_project" in table
            assert len(keys) == 2, f"{table} should have composite key"


class TestNormalizeTableRows:
    def test_keeps_array_rows(self) -> None:
        rows = [{"id": "first"}, {"id": "second"}]

        assert normalize_table_rows("users", rows) == rows

    def test_keeps_empty_array(self) -> None:
        assert normalize_table_rows("users", []) == []

    def test_wraps_single_object_as_one_row(self) -> None:
        row = {"id": "only"}

        assert normalize_table_rows("users", row) == [row]

    def test_treats_null_as_an_empty_table(self) -> None:
        assert normalize_table_rows("users", None) == []

    @pytest.mark.parametrize("value", ["row", 1, True])
    def test_rejects_non_table_shapes(self, value: object) -> None:
        with pytest.raises(
            RuntimeError,
            match=r"Table 'users' must be an array of objects or one object",
        ):
            normalize_table_rows("users", value)

    def test_rejects_non_object_array_rows(self) -> None:
        with pytest.raises(
            RuntimeError,
            match=r"Table 'users' row 1 must be an object; got str",
        ):
            normalize_table_rows("users", [{"id": "valid"}, "invalid"])


class TestImportTableShapes:
    @staticmethod
    def _write_json(path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def _write_export(cls, path: Path, data: object) -> None:
        cls._write_json(
            path,
            {"export_metadata": {"version": "1.0"}, "data": data},
        )

    @staticmethod
    def _run_import(
        tmp_path: Path,
        input_paths: list[Path],
    ) -> tuple[int, list[tuple[str, list[dict[str, object]]]]]:
        db_path = tmp_path / "forgetful.db"
        db_path.touch()
        imported: list[tuple[str, list[dict[str, object]]]] = []

        def record_import(
            _db_path: str,
            table: str,
            rows: list[dict[str, object]],
            _schema_columns: list[str],
            _merge_mode: str,
        ) -> tuple[int, int, int]:
            imported.append((table, rows))
            return len(rows), 0, 0

        input_args = [str(path) for path in input_paths]
        with (
            patch(
                "scripts.forgetful.import_forgetful_memories.get_schema_columns",
                return_value=["id"],
            ),
            patch(
                "scripts.forgetful.import_forgetful_memories.import_table",
                side_effect=record_import,
            ),
        ):
            result = main(
                [
                    "--input-files",
                    *input_args,
                    "--database-path",
                    str(db_path),
                    "--force",
                ]
            )
        return result, imported

    def test_malformed_table_reports_file_and_table(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        export_path = tmp_path / "malformed.json"
        self._write_export(export_path, {"users": "invalid"})

        result, imported = self._run_import(tmp_path, [export_path])

        assert result == 1
        assert imported == []
        assert (
            "FAIL malformed.json: Table 'users' must be an array of objects or one object"
            in capsys.readouterr().out
        )

    def test_malformed_later_table_preserves_prior_insert_count(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        export_path = tmp_path / "partially-malformed.json"
        self._write_export(
            export_path,
            {"users": [{"id": "valid"}], "projects": "invalid"},
        )

        result, imported = self._run_import(tmp_path, [export_path])

        assert result == 1
        assert imported == [("users", [{"id": "valid"}])]
        assert "Import completed with failures: 1 succeeded, 1 failed" in capsys.readouterr().out

    def test_committed_backup_allows_later_correction_export(
        self,
        tmp_path: Path,
    ) -> None:
        backup_path = (
            Path(__file__).resolve().parent.parent
            / ".forgetful"
            / "exports"
            / "2026-01-19-full-backup.json"
        )
        correction_path = tmp_path / "later-correction.json"
        self._write_export(correction_path, {"memories": [{"id": "later-correction"}]})

        result, imported = self._run_import(
            tmp_path,
            [backup_path, correction_path],
        )

        assert result == 0
        assert any(table == "users" and len(rows) == 1 for table, rows in imported)
        assert imported[-1] == ("memories", [{"id": "later-correction"}])

    def test_malformed_data_section_reports_file_and_allows_later_export(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        malformed_path = tmp_path / "malformed-data.json"
        self._write_export(malformed_path, [])
        correction_path = tmp_path / "correction.json"
        self._write_export(correction_path, {"memories": [{"id": "correction"}]})

        result, imported = self._run_import(
            tmp_path,
            [malformed_path, correction_path],
        )

        assert result == 1
        assert imported == [("memories", [{"id": "correction"}])]
        assert (
            "FAIL malformed-data.json: Data section must be an object of tables; got list"
            in capsys.readouterr().out
        )

    @pytest.mark.parametrize("root_value", [None, 7, True, []])
    def test_malformed_root_reports_file_and_allows_later_export(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        root_value: object,
    ) -> None:
        malformed_path = tmp_path / "malformed-root.json"
        self._write_json(malformed_path, root_value)
        correction_path = tmp_path / "correction.json"
        self._write_export(correction_path, {"memories": [{"id": "correction"}]})

        result, imported = self._run_import(
            tmp_path,
            [malformed_path, correction_path],
        )

        assert result == 1
        assert imported == [("memories", [{"id": "correction"}])]
        expected = (
            "FAIL malformed-root.json: "
            f"Export root must be an object; got {type(root_value).__name__}"
        )
        assert expected in capsys.readouterr().out


class TestImportTableWarnings:
    def _make_result(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["sqlite3"],
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_raises_on_non_unique_insert_failure(self) -> None:
        """Non-UNIQUE insert failures raise RuntimeError."""
        schema_check = self._make_result(stdout="0")
        insert_fail = self._make_result(returncode=1, stderr="CHECK constraint failed")
        with patch(
            "scripts.forgetful.import_forgetful_memories.run_sqlite3",
            side_effect=[schema_check, insert_fail],
        ):
            with pytest.raises(RuntimeError, match="CHECK constraint failed"):
                import_table(
                    "/fake/db",
                    "memories",
                    [{"id": 1, "content": "test"}],
                    ["id", "content"],
                    "skip",
                )

    def test_unique_constraint_skip_is_silent(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """UNIQUE constraint violations remain silent (intentional skips)."""
        schema_check = self._make_result(stdout="1")
        unique_fail = self._make_result(
            returncode=1,
            stderr="UNIQUE constraint failed: memories.id",
        )
        with patch(
            "scripts.forgetful.import_forgetful_memories.run_sqlite3",
            side_effect=[schema_check, unique_fail],
        ):
            inserted, updated, skipped = import_table(
                "/fake/db",
                "memories",
                [{"id": 1, "content": "test"}],
                ["id", "content"],
                "skip",
            )
        assert skipped == 1
        assert capsys.readouterr().err == ""
