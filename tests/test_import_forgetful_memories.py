"""Tests for scripts.forgetful.import_forgetful_memories module."""

from __future__ import annotations

import json

from scripts.forgetful.import_forgetful_memories import (
    IMPORT_ORDER,
    PRIMARY_KEYS,
    escape_sql_value,
)


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
