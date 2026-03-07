#!/usr/bin/env python3
"""Tests for schema_validation module.

Migrated from SchemaValidation.Tests.ps1 (Pester) to pytest.
Coverage target: all 4 exported functions.

Exit codes (ADR-035):
    0 - Success: all tests passed
    1 - Error: one or more tests failed
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from memory_core.schema_validation import (
    clear_schema_cache,
    get_schema_path,
    test_schema_valid,
    write_validated_json,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Clear schema cache before each test."""
    clear_schema_cache()


@pytest.fixture()
def test_dir(tmp_path: Path) -> Path:
    """Create a test directory with a minimal schema."""
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()

    test_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["id", "name", "items"],
        "properties": {
            "id": {"type": "string", "pattern": r"^test-\d+$"},
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "active": {"type": "boolean"},
            "status": {
                "type": "string",
                "enum": ["pending", "active", "complete"],
            },
            "items": {"type": "array"},
            "metadata": {"type": "object"},
        },
    }

    schema_path = schema_dir / "test.schema.json"
    schema_path.write_text(json.dumps(test_schema, indent=2), encoding="utf-8")

    return tmp_path


@pytest.fixture()
def schema_dir(test_dir: Path) -> Path:
    """Return the schema directory path."""
    return test_dir / "schemas"


# ---------------------------------------------------------------------------
# Get-SchemaPath tests
# ---------------------------------------------------------------------------


class TestGetSchemaPath:
    """Tests for get_schema_path function."""

    def test_loads_schema_file_successfully(self, schema_dir: Path) -> None:
        result = get_schema_path("test", schema_dir)
        assert result == schema_dir / "test.schema.json"

    def test_caches_schema_path_for_reuse(self, schema_dir: Path) -> None:
        first = get_schema_path("test", schema_dir)
        second = get_schema_path("test", schema_dir)
        assert first == second
        assert first == schema_dir / "test.schema.json"

    def test_throws_when_schema_file_not_found(self, schema_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Schema file not found"):
            get_schema_path("nonexistent", schema_dir)

    def test_throws_when_not_in_git_repo_and_no_directory(
        self, test_dir: Path
    ) -> None:
        original_dir = os.getcwd()
        try:
            os.chdir(test_dir)
            with pytest.raises(FileNotFoundError, match="Cannot determine git root"):
                get_schema_path("test")
        finally:
            os.chdir(original_dir)


# ---------------------------------------------------------------------------
# Test-SchemaValid tests
# ---------------------------------------------------------------------------


class TestTestSchemaValid:
    """Tests for test_schema_valid function."""

    class TestValidData:
        """Tests for valid data validation."""

        def test_validates_valid_data_successfully(
            self, schema_dir: Path
        ) -> None:
            data = {"id": "test-123", "name": "Test Item", "items": []}
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is True
            assert result.errors == []

        def test_accepts_data_with_all_fields(self, schema_dir: Path) -> None:
            data = {
                "id": "test-456",
                "name": "Full Test",
                "count": 10,
                "active": True,
                "status": "active",
                "items": [1, 2, 3],
                "metadata": {"key": "value"},
            }
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is True

        def test_accepts_json_string_input(self, schema_dir: Path) -> None:
            json_str = '{"id":"test-789","name":"JSON String","items":[]}'
            result = test_schema_valid(json_str, "test", schema_dir)
            assert result.valid is True

    class TestMissingRequiredFields:
        """Tests for missing required field detection."""

        def test_detects_missing_id_field(self, schema_dir: Path) -> None:
            data = {"name": "Missing ID", "items": []}
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert "Missing required field: 'id'" in result.errors

        def test_detects_missing_items_array(self, schema_dir: Path) -> None:
            data = {"id": "test-001", "name": "Missing Items"}
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert "Missing required field: 'items'" in result.errors

        def test_reports_multiple_missing_fields(
            self, schema_dir: Path
        ) -> None:
            data = {"name": "Only Name"}
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert len(result.errors) >= 2

    class TestTypeValidation:
        """Tests for type validation."""

        def test_detects_incorrect_string_type(
            self, schema_dir: Path
        ) -> None:
            data = {"id": 999, "name": "Test", "items": []}
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert len(result.errors) > 0

        def test_detects_incorrect_integer_type(
            self, schema_dir: Path
        ) -> None:
            data = {
                "id": "test-123",
                "name": "Test",
                "count": "not-a-number",
                "items": [],
            }
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert any(
                "Field 'count' should be integer" in e for e in result.errors
            )

        def test_detects_incorrect_boolean_type(
            self, schema_dir: Path
        ) -> None:
            data = {
                "id": "test-123",
                "name": "Test",
                "active": "yes",
                "items": [],
            }
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert any(
                "Field 'active' should be boolean" in e for e in result.errors
            )

        def test_detects_null_instead_of_array(
            self, schema_dir: Path
        ) -> None:
            data = {"id": "test-123", "name": "Test", "items": None}
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert any("Field 'items' is null" in e for e in result.errors)

        def test_detects_scalar_instead_of_array(
            self, schema_dir: Path
        ) -> None:
            data = {"id": "test-123", "name": "Test", "items": "single-item"}
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert any(
                "Field 'items' should be array" in e for e in result.errors
            )

    class TestConstraintValidation:
        """Tests for enum and pattern constraints."""

        def test_detects_enum_violation(self, schema_dir: Path) -> None:
            data = {
                "id": "test-123",
                "name": "Test",
                "status": "invalid-status",
                "items": [],
            }
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert any("not in allowed values" in e for e in result.errors)

        def test_detects_pattern_violation(self, schema_dir: Path) -> None:
            data = {
                "id": "invalid-format",
                "name": "Test",
                "items": [],
            }
            result = test_schema_valid(data, "test", schema_dir)
            assert result.valid is False
            assert any("does not match pattern" in e for e in result.errors)

    class TestErrorHandling:
        """Tests for error handling."""

        def test_handles_invalid_json_string_gracefully(
            self, schema_dir: Path
        ) -> None:
            result = test_schema_valid(
                '{"id":invalid json}', "test", schema_dir
            )
            assert result.valid is False
            assert any(
                "Failed to parse JSON content" in e for e in result.errors
            )

        def test_handles_missing_schema_file(self, schema_dir: Path) -> None:
            data = {"id": "test-123", "name": "Test", "items": []}
            result = test_schema_valid(data, "nonexistent", schema_dir)
            assert result.valid is False
            assert any("Failed to load schema" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Write-ValidatedJson tests
# ---------------------------------------------------------------------------


class TestWriteValidatedJson:
    """Tests for write_validated_json function."""

    class TestSuccessfulWrites:
        """Tests for successful write operations."""

        def test_writes_valid_data_to_file(
            self, test_dir: Path, schema_dir: Path
        ) -> None:
            output_file = test_dir / "output.json"
            data = {"id": "test-123", "name": "Test Item", "items": []}

            result = write_validated_json(
                data, output_file, "test", schema_dir
            )

            assert result.success is True
            assert result.file_path == str(output_file)
            assert output_file.exists()

        def test_creates_valid_json_file(
            self, test_dir: Path, schema_dir: Path
        ) -> None:
            output_file = test_dir / "output.json"
            data = {"id": "test-456", "name": "Valid JSON", "items": [1, 2, 3]}

            write_validated_json(data, output_file, "test", schema_dir)

            content = json.loads(output_file.read_text(encoding="utf-8"))
            assert content["id"] == "test-456"
            assert len(content["items"]) == 3

        def test_overwrites_file_with_force(
            self, test_dir: Path, schema_dir: Path
        ) -> None:
            output_file = test_dir / "output.json"
            data1 = {"id": "test-111", "name": "First", "items": []}
            write_validated_json(data1, output_file, "test", schema_dir)

            data2 = {"id": "test-222", "name": "Second", "items": []}
            result = write_validated_json(
                data2, output_file, "test", schema_dir, force=True
            )

            assert result.success is True
            content = json.loads(output_file.read_text(encoding="utf-8"))
            assert content["id"] == "test-222"

    class TestValidationFailures:
        """Tests for validation failures during write."""

        def test_fails_when_data_missing_required_fields(
            self, test_dir: Path, schema_dir: Path
        ) -> None:
            output_file = test_dir / "output.json"
            data = {"name": "Missing ID and items"}

            result = write_validated_json(
                data, output_file, "test", schema_dir
            )

            assert result.success is False
            assert result.validation_result.valid is False
            assert len(result.validation_result.errors) > 0
            assert not output_file.exists()

        def test_fails_when_data_has_wrong_types(
            self, test_dir: Path, schema_dir: Path
        ) -> None:
            output_file = test_dir / "output.json"
            data = {"id": 123, "name": "Test", "items": []}

            result = write_validated_json(
                data, output_file, "test", schema_dir
            )

            assert result.success is False
            assert not output_file.exists()

        def test_fails_when_file_exists_without_force(
            self, test_dir: Path, schema_dir: Path
        ) -> None:
            output_file = test_dir / "output.json"
            data = {"id": "test-111", "name": "First", "items": []}
            write_validated_json(data, output_file, "test", schema_dir)

            result = write_validated_json(
                data, output_file, "test", schema_dir
            )

            assert result.success is False
            assert any(
                "File already exists" in e
                for e in result.validation_result.errors
            )

    class TestRegressions821:
        """Regression tests for #821: array handling."""

        def test_preserves_empty_arrays_in_output(
            self, test_dir: Path, schema_dir: Path
        ) -> None:
            output_file = test_dir / "output.json"
            data = {"id": "test-999", "name": "Empty Arrays", "items": []}

            result = write_validated_json(
                data, output_file, "test", schema_dir
            )

            assert result.success is True
            content = json.loads(output_file.read_text(encoding="utf-8"))
            assert content["items"] == []

        def test_preserves_single_element_arrays_in_output(
            self, test_dir: Path, schema_dir: Path
        ) -> None:
            output_file = test_dir / "output.json"
            data = {
                "id": "test-888",
                "name": "Single Item Array",
                "items": ["one-item"],
            }

            result = write_validated_json(
                data, output_file, "test", schema_dir
            )

            assert result.success is True
            content = json.loads(output_file.read_text(encoding="utf-8"))
            assert content["items"] == ["one-item"]
            assert len(content["items"]) == 1


# ---------------------------------------------------------------------------
# Clear-SchemaCache tests
# ---------------------------------------------------------------------------


class TestClearSchemaCache:
    """Tests for clear_schema_cache function."""

    def test_clears_the_schema_cache(self, schema_dir: Path) -> None:
        # Load a schema to populate cache
        get_schema_path("test", schema_dir)

        # Clear cache
        clear_schema_cache()

        # Load again should work (cache was cleared, fresh load)
        result = get_schema_path("test", schema_dir)
        assert result == schema_dir / "test.schema.json"


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end integration tests."""

    def test_validate_and_write_episode_like_data(
        self, test_dir: Path, schema_dir: Path
    ) -> None:
        output_file = test_dir / "episode-integration-test.json"

        data = {
            "id": "test-777",
            "name": "Integration Test Episode",
            "status": "complete",
            "items": [
                {"type": "event", "content": "First event"},
                {"type": "event", "content": "Second event"},
            ],
            "metadata": {"created": "2026-01-01T00:00:00Z", "version": "1.0"},
        }

        result = write_validated_json(data, output_file, "test", schema_dir)

        assert result.success is True
        assert output_file.exists()

        content = json.loads(output_file.read_text(encoding="utf-8"))
        assert content["id"] == "test-777"
        assert len(content["items"]) == 2
