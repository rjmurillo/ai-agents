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


def _validate_metadata_string_field(metadata: dict, field: str) -> list[str]:
    """Validate one of Metadata's required string sub-fields (Script, Timestamp).

    skill-output.schema.json types both `"Script"` and `"Timestamp"` as
    `"type": "string"`. Checking only truthiness let a non-string value
    (for example `{"Script": 1, "Timestamp": 1}`) pass silently, so the
    validator disagreed with the schema it claims to enforce (Copilot
    review on PR #5283, commit 6639555b8). Does not additionally enforce
    Timestamp's `"format": "date-time"`: JSON Schema draft-07 treats
    `format` as an annotation validators may choose to assert, and this
    validator does not carry a date-time parser dependency for it.
    """
    errors: list[str] = []
    value = metadata.get(field)
    if not value:
        errors.append(f"Metadata.{field} is required")
    elif not isinstance(value, str):
        errors.append(f"Metadata.{field} must be a string, got: {type(value).__name__}")
    return errors


def _validate_metadata_version_field(metadata: dict) -> list[str]:
    """Validate Metadata.Version: optional, but must be a string when present.

    skill-output.schema.json types `"Version"` as `"type": "string"` but
    does not list it in Metadata's `required` array (unlike Script and
    Timestamp). A present-but-wrong-typed value (for example
    `{"Version": 1}`) previously passed silently because nothing checked
    it, disagreeing with the schema (Copilot review on PR #5283). Absent
    is valid per the schema; only a type mismatch on a present value is
    an error.
    """
    if "Version" not in metadata:
        return []
    value = metadata["Version"]
    if not isinstance(value, str):
        return [f"Metadata.Version must be a string, got: {type(value).__name__}"]
    return []


def _validate_metadata_field(data: dict) -> list[str]:
    """Validate the envelope's Metadata field: present, an object, Script, Timestamp, Version.

    skill-output.schema.json requires Metadata to be `"type": "object"`. A
    schema-invalid non-dict value (a string, array, or number) previously
    reached `metadata.get(...)` unchecked and crashed with AttributeError
    (`'str' object has no attribute 'get'`) instead of producing a
    validation finding, the same class of gap already fixed for `Error`
    (AI Spec Validator finding on PR #5283, commit 6bee062d8).
    """
    errors: list[str] = []
    if "Metadata" not in data:
        errors.append("Missing required field: Metadata")
    else:
        metadata = data["Metadata"]
        if not isinstance(metadata, dict):
            errors.append(
                f"Metadata must be an object, got: {type(metadata).__name__}"
            )
        else:
            errors.extend(_validate_metadata_string_field(metadata, "Script"))
            errors.extend(_validate_metadata_string_field(metadata, "Timestamp"))
            errors.extend(_validate_metadata_version_field(metadata))
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


def _validate_error_message_and_code(error_field: dict) -> list[str]:
    """Validate Error.Message (string) and Error.Code (integer).

    skill-output.schema.json types `Message` as `"type": "string",
    "minLength": 1` and `Code` as `"type": "integer"`. Checking only
    truthiness/presence let `{"Message": 123, "Code": "one"}` pass,
    disagreeing with the schema (Copilot review on PR #5283, commit
    6639555b8). `bool` is excluded from the integer check: Python's
    `bool` subclasses `int`, so `isinstance(True, int)` is `True`, but a
    JSON boolean is not a JSON integer. The `not message` branch below
    already rejects both a missing key and an empty string (`""` is
    falsy), so it independently enforces the schema's `minLength: 1`
    without a separate length check.
    """
    errors: list[str] = []
    message = error_field.get("Message")
    if not message:
        errors.append("Error.Message is required")
    elif not isinstance(message, str):
        errors.append(f"Error.Message must be a string, got: {type(message).__name__}")

    if "Code" not in error_field:
        errors.append("Error.Code is required")
    else:
        code = error_field["Code"]
        if isinstance(code, bool) or not isinstance(code, int):
            errors.append(f"Error.Code must be an integer, got: {type(code).__name__}")

    return errors


def _validate_error_field(data: dict) -> list[str]:
    """Validate the envelope's Error field.

    Error is a required key per the schema's top-level `required` array
    (ADR-103 Decision item 1); its value is `oneOf(null, object)`. A
    missing key and an explicit `null` value are distinct under the
    schema (only the latter satisfies the `oneOf`), so `data.get("Error")`
    alone cannot tell them apart; checked separately below (Copilot
    review on PR #5283, commit 6639555b8).

    Error is additionally required to be non-null when Success=false (an
    envelope-level rule, not part of the schema's Error sub-object
    contract). Independent of Success, a non-null, non-dict value (an
    array, string, or number) is neither `oneOf` branch and must be
    rejected rather than silently ignored, and a `Success: true` envelope
    carrying a malformed `Error` object (still schema-invalid) must not
    pass silently either (ADR-103, Copilot review on PR #5283, commit
    508917d4b).
    """
    errors: list[str] = []
    if "Error" not in data:
        errors.append("Missing required field: Error")

    error_field = data.get("Error")
    if data.get("Success") is False and error_field is None:
        errors.append("Error field is required when Success is false")

    if error_field is not None and not isinstance(error_field, dict):
        errors.append(
            f"Error must be null or an object, got: {type(error_field).__name__}"
        )
    elif isinstance(error_field, dict):
        errors.extend(_validate_error_message_and_code(error_field))
        errors.extend(_validate_error_type(error_field.get("Type")))

    return errors


def validate_envelope(data: object) -> list[str]:
    """Validate the output envelope against ADR-056 schema, as corrected by ADR-103.

    Sergeant method: delegates each field's contract to a dedicated
    helper and collects their findings. Split from a single 15-branch
    function (taste-lint complexity gate, max 10) into per-field helpers
    once the Data-field and Error-shape checks pushed this function over
    the limit.

    Args:
        data: The result of `json.loads()` on the candidate envelope. Any
            JSON value may arrive here (object, array, string, number,
            bool, or null); only an object can be schema-valid.

    Returns:
        List of validation error messages. Empty list means valid.
    """
    # skill-output.schema.json's top level is `"type": "object"`. The type
    # annotation above (`data: dict`) is not enforced at runtime: the CLI
    # passes `json.loads()`'s result straight through, and valid JSON such
    # as `null`, `1`, or `[]` reaches here. Without this guard, `"Success"
    # not in data` raises TypeError for `None`/`1` (not iterable), and an
    # array reaches `data["Metadata"]` and raises TypeError, instead of
    # producing a finding and exit code 1 (Copilot review on PR #5283,
    # commit 6639555b8).
    if not isinstance(data, dict):
        return [f"Envelope must be a JSON object, got: {type(data).__name__}"]

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
