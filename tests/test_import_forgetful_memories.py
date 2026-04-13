"""Tests for scripts.forgetful.import_forgetful_memories module."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from scripts.forgetful.import_forgetful_memories import (
    IMPORT_ORDER,
    PRIMARY_KEYS,
    escape_sql_value,
    import_table,
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


class TestImportTableWarnings:
    def _make_result(
        self, returncode: int = 0, stdout: str = "", stderr: str = "",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["sqlite3"], returncode=returncode, stdout=stdout, stderr=stderr,
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
                    "/fake/db", "memories", [{"id": 1, "content": "test"}],
                    ["id", "content"], "skip",
                )

    def test_unique_constraint_skip_is_silent(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """UNIQUE constraint violations remain silent (intentional skips)."""
        schema_check = self._make_result(stdout="1")
        unique_fail = self._make_result(
            returncode=1, stderr="UNIQUE constraint failed: memories.id",
        )
        with patch(
            "scripts.forgetful.import_forgetful_memories.run_sqlite3",
            side_effect=[schema_check, unique_fail],
        ):
            inserted, updated, skipped = import_table(
                "/fake/db", "memories", [{"id": 1, "content": "test"}],
                ["id", "content"], "skip",
            )
        assert skipped == 1
        assert capsys.readouterr().err == ""
