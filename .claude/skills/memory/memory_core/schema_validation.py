#!/usr/bin/env python3
"""Schema validation module for JSON output validation.

Provides fail-fast JSON schema validation for memory system producers.
Implements CVA pattern: shared validation logic extracted from multiple scripts.

Functions:
    get_schema_path: Load and cache schema paths.
    test_schema_valid: Validate JSON against schema.
    write_validated_json: Validate-then-write pattern.
    clear_schema_cache: Reset cache (for testing).

Exit codes (ADR-035):
    0 - Success
    1 - Logic error (validation failure)
    2 - Config error (schema not found)
    3 - External error (I/O failure)
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Module-level schema cache
_schema_cache: dict[str, Path] = {}


@dataclass
class ValidationResult:
    """Result of a schema validation check."""

    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class WriteResult:
    """Result of a validated JSON write operation."""

    success: bool
    file_path: str
    validation_result: ValidationResult


def clear_schema_cache() -> None:
    """Clear the schema path cache (for testing)."""
    _schema_cache.clear()


def get_schema_path(
    schema_name: str,
    schema_directory: str | Path | None = None,
) -> Path:
    """Load and cache a schema file path.

    Args:
        schema_name: Name of the schema file (without extension).
        schema_directory: Directory containing schema files.
            Defaults to .claude/skills/memory/resources/schemas/ under git root.

    Returns:
        Full path to the schema file.

    Raises:
        FileNotFoundError: If the schema file or git root cannot be found.
    """
    if schema_name in _schema_cache:
        return _schema_cache[schema_name]

    if schema_directory is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            git_root = result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            msg = (
                "Cannot determine git root. "
                "Run from within a git repository or provide schema_directory."
            )
            raise FileNotFoundError(msg) from err
        schema_directory = (
            Path(git_root) / ".claude" / "skills" / "memory" / "resources" / "schemas"
        )

    schema_directory = Path(schema_directory)
    schema_file = (schema_directory / f"{schema_name}.schema.json").resolve()
    if not schema_file.is_relative_to(Path(schema_directory).resolve()):
        msg = f"Path traversal attempt detected for schema: {schema_name}"
        raise FileNotFoundError(msg)

    if not schema_file.is_file():
        msg = f"Schema file not found: {schema_file}"
        raise FileNotFoundError(msg)

    _schema_cache[schema_name] = schema_file
    return schema_file


def _check_type(
    field_name: str,
    field_value: Any,
    expected_type: str,
    field_schema: dict[str, Any],
) -> list[str]:
    """Check a single field value against its declared JSON Schema type.

    Returns a list of error strings (empty if valid).
    """
    errors: list[str] = []

    if expected_type == "string":
        if field_value is not None and not isinstance(field_value, str):
            errors.append(
                f"Field '{field_name}' should be string, "
                f"got {type(field_value).__name__}"
            )

    elif expected_type == "number":
        if field_value is not None and not isinstance(field_value, (int, float)):
            errors.append(
                f"Field '{field_name}' should be number, "
                f"got {type(field_value).__name__}"
            )

    elif expected_type == "integer":
        # In JSON, booleans are not integers even though bool is subclass of int
        if field_value is not None and (
            not isinstance(field_value, int) or isinstance(field_value, bool)
        ):
            errors.append(
                f"Field '{field_name}' should be integer, "
                f"got {type(field_value).__name__}"
            )

    elif expected_type == "boolean":
        if field_value is not None and not isinstance(field_value, bool):
            errors.append(
                f"Field '{field_name}' should be boolean, "
                f"got {type(field_value).__name__}"
            )

    elif expected_type == "array":
        if field_value is None:
            errors.append(
                f"Field '{field_name}' is null, should be array "
                "(use [] for empty array)"
            )
        elif not isinstance(field_value, list):
            errors.append(
                f"Field '{field_name}' should be array, "
                f"got {type(field_value).__name__}"
            )

    elif expected_type == "object":
        if field_value is not None and not isinstance(field_value, dict):
            errors.append(
                f"Field '{field_name}' should be object, "
                f"got {type(field_value).__name__}"
            )

    return errors


def test_schema_valid(
    json_content: str | dict[str, Any] | Any,
    schema_name: str,
    schema_directory: str | Path | None = None,
) -> ValidationResult:
    """Validate JSON data against a JSON schema.

    Performs basic structure validation: required fields, types, enums, patterns.

    Args:
        json_content: JSON content as a string, dict, or other object.
        schema_name: Name of the schema to validate against.
        schema_directory: Optional directory containing schema files.

    Returns:
        ValidationResult with valid flag and list of error messages.
    """
    errors: list[str] = []

    # Get schema path
    try:
        schema_path = get_schema_path(schema_name, schema_directory)
    except (FileNotFoundError, OSError) as exc:
        errors.append(f"Failed to load schema '{schema_name}': {exc}")
        return ValidationResult(valid=False, errors=errors)

    # Load schema
    try:
        schema_text = schema_path.read_text(encoding="utf-8")
        schema = json.loads(schema_text)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Failed to parse schema file '{schema_path}': {exc}")
        return ValidationResult(valid=False, errors=errors)

    # Parse JSON content if string
    data = json_content
    if isinstance(json_content, str):
        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as exc:
            errors.append(f"Failed to parse JSON content: {exc}")
            return ValidationResult(valid=False, errors=errors)

    # Check required fields
    required_fields = schema.get("required", [])
    for required_field in required_fields:
        if not isinstance(data, dict) or required_field not in data:
            errors.append(f"Missing required field: '{required_field}'")

    # Check field types
    properties = schema.get("properties", {})
    if isinstance(data, dict):
        for field_name, field_schema in properties.items():
            if field_name not in data:
                continue

            field_value = data[field_name]

            # Null check for required fields
            if field_value is None and field_schema.get("type") != "null":
                if field_name in required_fields:
                    errors.append(
                        f"Field '{field_name}' is null but is required"
                    )
                continue

            # Type validation
            field_type = field_schema.get("type")
            if field_type:
                errors.extend(
                    _check_type(field_name, field_value, field_type, field_schema)
                )

            # Enum constraints
            enum_values = field_schema.get("enum")
            if enum_values and field_value is not None:
                if field_value not in enum_values:
                    allowed = ", ".join(str(v) for v in enum_values)
                    errors.append(
                        f"Field '{field_name}' value '{field_value}' "
                        f"not in allowed values: {allowed}"
                    )

            # Pattern constraints (for strings)
            pattern = field_schema.get("pattern")
            if pattern and field_value is not None and isinstance(field_value, str):
                if not re.search(pattern, field_value):
                    errors.append(
                        f"Field '{field_name}' value '{field_value}' "
                        f"does not match pattern: {pattern}"
                    )

    return ValidationResult(valid=len(errors) == 0, errors=errors)


# Prevent pytest from collecting this production function as a test
setattr(test_schema_valid, "__test__", False)  # noqa: B010


def write_validated_json(
    data: Any,
    file_path: str | Path,
    schema_name: str,
    schema_directory: str | Path | None = None,
    depth: int = 10,
    force: bool = False,
) -> WriteResult:
    """Validate JSON against schema before writing to file (fail-fast pattern).

    Args:
        data: Data object to serialize and validate.
        file_path: Destination file path.
        schema_name: Name of the schema to validate against.
        schema_directory: Optional directory containing schema files.
        depth: JSON serialization depth (unused in Python, kept for API compat).
        force: Overwrite file if it exists.

    Returns:
        WriteResult with success flag, file path, and validation result.
    """
    file_path = str(file_path)

    # Serialize to JSON
    try:
        json_str = json.dumps(data, indent=2, default=str)
    except (TypeError, ValueError) as exc:
        return WriteResult(
            success=False,
            file_path=file_path,
            validation_result=ValidationResult(
                valid=False,
                errors=[f"Failed to serialize to JSON: {exc}"],
            ),
        )

    # Validate against schema
    validation_result = test_schema_valid(
        json_str, schema_name, schema_directory
    )

    if not validation_result.valid:
        return WriteResult(
            success=False,
            file_path=file_path,
            validation_result=validation_result,
        )

    # Check file existence
    path_obj = Path(file_path)
    if path_obj.exists() and not force:
        return WriteResult(
            success=False,
            file_path=file_path,
            validation_result=ValidationResult(
                valid=False,
                errors=[f"File already exists: {file_path} (use force=True to overwrite)"],
            ),
        )

    # Write to file
    try:
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(json_str, encoding="utf-8")
    except OSError as exc:
        return WriteResult(
            success=False,
            file_path=file_path,
            validation_result=ValidationResult(
                valid=False,
                errors=[f"Failed to write file '{file_path}': {exc}"],
            ),
        )

    return WriteResult(
        success=True,
        file_path=file_path,
        validation_result=validation_result,
    )
