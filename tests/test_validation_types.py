"""Tests for scripts.validation.types and the assert_validation_result helper.

Verifies the shared ValidationResult dataclass and the test helper
introduced by issue #839.
"""

from __future__ import annotations

import pytest

from scripts.validation.types import ValidationResult
from tests.conftest import assert_validation_result


class TestValidationResult:
    """Tests for the shared ValidationResult dataclass."""

    def test_default_is_valid(self) -> None:
        """Empty result is valid."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_errors_make_invalid(self) -> None:
        """Result with errors is invalid."""
        result = ValidationResult(errors=["something broke"])
        assert result.is_valid is False

    def test_warnings_only_is_valid(self) -> None:
        """Warnings alone do not affect validity."""
        result = ValidationResult(warnings=["heads up"])
        assert result.is_valid is True

    def test_is_valid_updates_after_append(self) -> None:
        """is_valid reflects current errors list state."""
        result = ValidationResult()
        assert result.is_valid is True

        result.errors.append("new error")
        assert result.is_valid is False

    def test_is_valid_restored_after_clear(self) -> None:
        """Clearing errors restores validity."""
        result = ValidationResult(errors=["temp"])
        result.errors.clear()
        assert result.is_valid is True


class TestAssertValidationResult:
    """Tests for the assert_validation_result helper."""

    def test_valid_result_passes(self) -> None:
        """Helper passes for a valid result."""
        result = ValidationResult()
        assert_validation_result(result, is_valid=True)

    def test_invalid_result_passes(self) -> None:
        """Helper passes for an invalid result with matching checks."""
        result = ValidationResult(errors=["missing field: name"])
        assert_validation_result(
            result,
            is_valid=False,
            error_count=1,
            error_substring="missing field",
        )

    def test_wrong_validity_fails(self) -> None:
        """Helper raises AssertionError on validity mismatch."""
        result = ValidationResult(errors=["err"])
        with pytest.raises(AssertionError, match="Expected is_valid=True"):
            assert_validation_result(result, is_valid=True)

    def test_wrong_error_count_fails(self) -> None:
        """Helper raises AssertionError on error count mismatch."""
        result = ValidationResult(errors=["a", "b"])
        with pytest.raises(AssertionError, match="Expected 1 errors"):
            assert_validation_result(result, is_valid=False, error_count=1)

    def test_missing_error_substring_fails(self) -> None:
        """Helper raises AssertionError when substring not found."""
        result = ValidationResult(errors=["something else"])
        with pytest.raises(AssertionError, match="No error contains"):
            assert_validation_result(
                result,
                is_valid=False,
                error_substring="not present",
            )

    def test_warning_checks(self) -> None:
        """Helper validates warning count and substring."""
        result = ValidationResult(warnings=["deprecation notice"])
        assert_validation_result(
            result,
            is_valid=True,
            warning_count=1,
            warning_substring="deprecation",
        )
