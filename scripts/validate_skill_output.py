"""Validate skill script output against the standard envelope schema (ADR-056, ADR-103).

Accepts JSON input from stdin or a file path and validates it against
the skill-output.schema.json schema. Returns exit code 0 for valid,
1 for invalid output.

Related: ADR-056 (Skill Output Format Standardization)
Related: ADR-103 (Python contract correction; Error.Type is required)

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
    (
        "NotFound",
        "ApiError",
        "AuthError",
        "InvalidParams",
        "RateLimitError",
        "Timeout",
        "General",
        "VerificationFailed",
    )
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


def _validate_success_field(data: dict) -> list[str]:
    """Validate the envelope's Success field: present, and a bool."""
    errors: list[str] = []
    if "Success" not in data:
        errors.append("Missing required field: Success")
    elif not isinstance(data["Success"], bool):
        errors.append(
            f"Field 'Success' must be a boolean, got: {type(data['Success']).__name__}"
        )
    return errors


def _validate_metadata_field(data: dict) -> list[str]:
    """Validate the envelope's Metadata field: present, Script, Timestamp."""
    errors: list[str] = []
    if "Metadata" not in data:
        errors.append("Missing required field: Metadata")
    else:
        metadata = data["Metadata"]
        if not metadata.get("Script"):
            errors.append("Metadata.Script is required")
        if not metadata.get("Timestamp"):
            errors.append("Metadata.Timestamp is required")
    return errors


def _validate_error_type(error_type: object) -> list[str]:
    """Validate the Error.Type sub-field in isolation.

    Checks the JSON type before the `in VALID_ERROR_TYPES` membership
    test: VALID_ERROR_TYPES is a frozenset, and `x in frozenset(...)`
    raises TypeError for an unhashable `x` (a list or dict) rather than
    returning False. A schema-invalid Type value (list, dict, int) must
    produce a validation finding, not crash the validator (Copilot review
    on PR #5283, commit 508917d4b).
    """
    errors: list[str] = []
    if error_type is None or error_type == "":
        errors.append("Error.Type is required")
    elif not isinstance(error_type, str):
        errors.append(
            f"Error.Type must be a string, got: {type(error_type).__name__}"
        )
    elif error_type not in VALID_ERROR_TYPES:
        valid_str = ", ".join(sorted(VALID_ERROR_TYPES))
        errors.append(
            f"Error.Type '{error_type}' is not valid. Must be one of: {valid_str}"
        )
    return errors


def _validate_error_field(data: dict) -> list[str]:
    """Validate the envelope's Error field.

    Error is required (non-null) when Success=false (an envelope-level
    rule, not part of the schema's Error sub-object contract). Independent
    of Success, skill-output.schema.json's Error property is
    `oneOf(null, object)`: a non-null, non-dict value (an array, string, or
    number) is neither branch and must be rejected rather than silently
    ignored, and a `Success: true` envelope carrying a malformed `Error`
    object (still schema-invalid) must not pass silently either (ADR-103,
    Copilot review on PR #5283, commit 508917d4b).
    """
    errors: list[str] = []
    error_field = data.get("Error")
    if data.get("Success") is False and error_field is None:
        errors.append("Error field is required when Success is false")

    if error_field is not None and not isinstance(error_field, dict):
        errors.append(
            f"Error must be null or an object, got: {type(error_field).__name__}"
        )
    elif isinstance(error_field, dict):
        if not error_field.get("Message"):
            errors.append("Error.Message is required")
        if "Code" not in error_field:
            errors.append("Error.Code is required")
        errors.extend(_validate_error_type(error_field.get("Type")))

    return errors


def validate_envelope(data: dict) -> list[str]:
    """Validate the output envelope against ADR-056 schema, as corrected by ADR-103.

    Sergeant method: delegates each field's contract to a dedicated
    helper and collects their findings. Split from a single 15-branch
    function (taste-lint complexity gate, max 10) into per-field helpers
    once the Data-field and Error-shape checks pushed this function over
    the limit.

    Args:
        data: Parsed JSON object.

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors: list[str] = []
    errors.extend(_validate_success_field(data))

    # ADR-103 Decision item 1 (unchanged from ADR-056): every envelope MUST
    # carry a Data key (null on failure, per the schema's own description
    # of the property). The schema's top-level `required` array omitted
    # "Data" until this fix, the same documented-but-unenforced gap this
    # ADR closed for Error.Type (independent-thinker seat, adr-review
    # debate on PR #5283).
    if "Data" not in data:
        errors.append("Missing required field: Data")

    errors.extend(_validate_metadata_field(data))
    errors.extend(_validate_error_field(data))
    return errors


def main() -> int:
    """Run validation and return exit code."""
    parser = argparse.ArgumentParser(
        description="Validate skill output against ADR-056/ADR-103 envelope schema."
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

    print("[PASS] Skill output conforms to ADR-056/ADR-103 envelope schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
