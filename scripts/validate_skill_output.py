"""Validate skill script output against the standard envelope schema (ADR-051).

Accepts JSON input from stdin or a file path and validates it against
the skill-output.schema.json schema. Returns exit code 0 for valid,
1 for invalid output.

Related: ADR-051 (Skill Output Format Standardization)

Usage:
    python3 scripts/validate_skill_output.py < output.json
    python3 scripts/validate_skill_output.py --input-file output.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

VALID_ERROR_TYPES = frozenset(
    ("NotFound", "ApiError", "AuthError", "InvalidParams", "Timeout", "General")
)


def _resolve_allowed_dir() -> Path:
    """Return the repo root directory for path traversal protection."""
    return Path(__file__).resolve().parent.parent


def _validate_file_path(file_path: str, allowed_dir: Path) -> Path:
    """Validate file path is within allowed directory (CWE-22 protection).

    Args:
        file_path: The user-provided file path.
        allowed_dir: The directory files must reside within.

    Returns:
        The resolved, validated path.

    Raises:
        SystemExit: If path traversal or symlink attack detected.
    """
    original = Path(file_path)
    resolved = original.resolve()

    # Check path is within allowed directory
    try:
        resolved.relative_to(allowed_dir)
    except ValueError:
        print("[FAIL] Path traversal attempt detected. Input file must be within the repository.")
        sys.exit(1)

    if not resolved.exists():
        print(f"[FAIL] File not found: {resolved}")
        sys.exit(1)

    # Check symlinks against original path, not resolved (CWE-22 symlink bypass)
    if original.is_symlink():
        real_path = Path(os.path.realpath(original))
        try:
            real_path.relative_to(allowed_dir)
        except ValueError:
            print(
                "[FAIL] Path traversal attempt detected. "
                "Input file must be within the repository."
            )
            sys.exit(1)

    return resolved


def validate_envelope(data: dict) -> list[str]:
    """Validate the output envelope against ADR-051 schema.

    Args:
        data: Parsed JSON object.

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

    # Validate required fields
    if "Success" not in data:
        errors.append("Missing required field: Success")
    elif not isinstance(data["Success"], bool):
        errors.append(
            f"Field 'Success' must be a boolean, got: {type(data['Success']).__name__}"
        )

    if "Metadata" not in data:
        errors.append("Missing required field: Metadata")
    else:
        metadata = data["Metadata"]
        if not metadata.get("Script"):
            errors.append("Metadata.Script is required")
        if not metadata.get("Timestamp"):
            errors.append("Metadata.Timestamp is required")

    # Validate error envelope when Success=false
    if data.get("Success") is False:
        error_field = data.get("Error")
        if error_field is None:
            errors.append("Error field is required when Success is false")
        elif isinstance(error_field, dict):
            if not error_field.get("Message"):
                errors.append("Error.Message is required")
            if "Code" not in error_field:
                errors.append("Error.Code is required")
            error_type = error_field.get("Type")
            if error_type and error_type not in VALID_ERROR_TYPES:
                valid_str = ", ".join(sorted(VALID_ERROR_TYPES))
                errors.append(
                    f"Error.Type '{error_type}' is not valid. Must be one of: {valid_str}"
                )

    return errors


def main() -> int:
    """Run validation and return exit code."""
    parser = argparse.ArgumentParser(
        description="Validate skill output against ADR-051 envelope schema."
    )
    parser.add_argument(
        "--input-file",
        default="-",
        help="Path to a JSON file to validate. Use '-' or omit to read from stdin.",
    )
    args = parser.parse_args()

    # Read input
    if args.input_file == "-":
        json_text = sys.stdin.read()
    else:
        allowed_dir = _resolve_allowed_dir()
        validated_path = _validate_file_path(args.input_file, allowed_dir)
        json_text = validated_path.read_text(encoding="utf-8")

    if not json_text or not json_text.strip():
        print("[FAIL] Empty input -- no JSON to validate")
        return 1

    # Parse JSON
    try:
        output = json.loads(json_text)
    except json.JSONDecodeError as exc:
        print(f"[FAIL] Invalid JSON: {exc}")
        return 1

    # Validate
    errors = validate_envelope(output)

    if errors:
        print("[FAIL] Skill output validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[PASS] Skill output conforms to ADR-051 envelope schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
