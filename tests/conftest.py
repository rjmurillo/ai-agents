"""Shared pytest fixtures and configuration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validation.types import ValidationResult  # noqa: E402


def assert_validation_result(
    result: ValidationResult,
    *,
    is_valid: bool,
    error_count: int | None = None,
    warning_count: int | None = None,
    error_substring: str | None = None,
    warning_substring: str | None = None,
) -> None:
    """Assert properties of a ValidationResult.

    Args:
        result: The ValidationResult to check.
        is_valid: Expected validity.
        error_count: Expected number of errors (None to skip check).
        warning_count: Expected number of warnings (None to skip check).
        error_substring: Substring that must appear in at least one error.
        warning_substring: Substring that must appear in at least one warning.
    """
    assert result.is_valid is is_valid, (
        f"Expected is_valid={is_valid}, got {result.is_valid}. "
        f"Errors: {result.errors}"
    )
    if error_count is not None:
        assert len(result.errors) == error_count, (
            f"Expected {error_count} errors, got {len(result.errors)}: "
            f"{result.errors}"
        )
    if warning_count is not None:
        assert len(result.warnings) == warning_count, (
            f"Expected {warning_count} warnings, got {len(result.warnings)}: "
            f"{result.warnings}"
        )
    if error_substring is not None:
        assert any(error_substring in e for e in result.errors), (
            f"No error contains '{error_substring}'. Errors: {result.errors}"
        )
    if warning_substring is not None:
        assert any(warning_substring in w for w in result.warnings), (
            f"No warning contains '{warning_substring}'. "
            f"Warnings: {result.warnings}"
        )


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def temp_test_dir(tmp_path: Path) -> Path:
    """Create and return a temporary directory for test files."""
    test_dir = tmp_path / "test_workspace"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir
