"""Mock fidelity validation helpers.

Validates that mock data used in tests matches the shape of real GitHub API
responses. This prevents mock drift where tests pass against mocks that no
longer reflect actual API behavior.

See: https://github.com/rjmurillo/ai-agents/issues/444
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "github_api"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a GitHub API fixture file by name (without .json extension).

    Args:
        name: Fixture name (e.g., "issue", "pull_request", "review_thread").

    Returns:
        Parsed JSON fixture as a dict.

    Raises:
        FileNotFoundError: If the fixture file does not exist.
        ValueError: If a path traversal attempt is detected.
    """
    fixture_path = (_FIXTURES_DIR / f"{name}.json").resolve()
    base_dir = _FIXTURES_DIR.resolve()

    if not fixture_path.is_relative_to(base_dir):
        raise ValueError(f"Path traversal attempt detected for fixture '{name}'")

    with open(fixture_path) as f:
        data: dict[str, Any] = json.load(f)
        return data


def get_fixture_keys(name: str) -> set[str]:
    """Get the set of keys from a fixture, excluding metadata keys.

    Args:
        name: Fixture name (e.g., "issue", "pull_request").

    Returns:
        Set of expected keys (excluding keys starting with '_').
    """
    fixture = load_fixture(name)
    return {k for k in fixture if not k.startswith("_")}


def assert_mock_keys_match(
    mock_data: dict[str, Any],
    fixture_name: str,
    *,
    allow_extra: bool = False,
    allow_missing: bool = False,
) -> None:
    """Assert that a mock dict's keys match the fixture's keys.

    This catches the most common mock drift issue: property name mismatches
    (e.g., PascalCase vs camelCase, missing fields, extra fields).

    Args:
        mock_data: The mock data dict used in tests.
        fixture_name: Name of the fixture to compare against.
        allow_extra: If True, extra keys in mock_data are allowed.
        allow_missing: If True, missing keys in mock_data are allowed.

    Raises:
        AssertionError: If keys don't match (with details about the mismatch).
    """
    expected = get_fixture_keys(fixture_name)
    actual = set(mock_data.keys())

    missing = expected - actual
    extra = actual - expected

    errors = []
    if missing and not allow_missing:
        errors.append(f"Missing keys (in fixture but not mock): {sorted(missing)}")
    if extra and not allow_extra:
        errors.append(f"Extra keys (in mock but not fixture): {sorted(extra)}")

    if errors:
        msg = (
            f"Mock shape mismatch for '{fixture_name}' fixture.\n"
            + "\n".join(errors)
            + f"\nExpected keys: {sorted(expected)}"
            + f"\nActual keys:   {sorted(actual)}"
        )
        raise AssertionError(msg)


def assert_mock_types_match(
    mock_data: dict[str, Any],
    fixture_name: str,
) -> None:
    """Assert that mock values have the same types as the fixture values.

    Checks top-level value types only (not nested structure). Skips None
    values in either mock or fixture since they represent absent data.

    Args:
        mock_data: The mock data dict used in tests.
        fixture_name: Name of the fixture to compare against.

    Raises:
        AssertionError: If any value type doesn't match.
    """
    fixture = load_fixture(fixture_name)
    errors = []

    for key in set(mock_data) & set(fixture):
        if key.startswith("_"):
            continue
        mock_val = mock_data[key]
        fixture_val = fixture[key]
        if mock_val is None or fixture_val is None:
            continue
        if type(mock_val) is not type(fixture_val):
            errors.append(
                f"  {key}: expected {type(fixture_val).__name__}, "
                f"got {type(mock_val).__name__}"
            )

    if errors:
        msg = (
            f"Mock type mismatch for '{fixture_name}' fixture:\n"
            + "\n".join(errors)
        )
        raise AssertionError(msg)
