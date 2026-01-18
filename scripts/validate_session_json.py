#!/usr/bin/env python3
"""Validate session logs in JSON format against schema.

Simple, unambiguous validation using JSON schema instead of regex parsing.

This is a Python port of Validate-SessionJson.ps1 following ADR-042 migration.

EXIT CODES:
  0  - Success: Session log is valid
  1  - Error: Session log validation failed (invalid JSON, missing fields, or schema violations)
  2  - Error: Unexpected error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Result of session log validation."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return True if no errors were found."""
        return len(self.errors) == 0


# Required session fields
REQUIRED_SESSION_FIELDS = frozenset({"number", "date", "branch", "startingCommit", "objective"})

# Branch naming pattern
BRANCH_PATTERN = re.compile(r"^(feat|fix|docs|chore|refactor|test|ci)/")

# Commit SHA pattern
COMMIT_SHA_PATTERN = re.compile(r"^[a-f0-9]{7,40}$")

# Session start MUST items
SESSION_START_MUST_ITEMS = frozenset({
    "serenaActivated",
    "serenaInstructions",
    "handoffRead",
    "sessionLogCreated",
    "branchVerified",
    "notOnMain",
})

# Session end MUST items
SESSION_END_MUST_ITEMS = frozenset({
    "checklistComplete",
    "handoffNotUpdated",
    "serenaMemoryUpdated",
    "markdownLintRun",
    "changesCommitted",
    "validationPassed",
})


def get_case_insensitive(data: dict[str, Any], key: str) -> Any | None:
    """Get value from dict with case-insensitive key lookup.

    Args:
        data: Dictionary to search.
        key: Key to find (case-insensitive).

    Returns:
        Value if found, None otherwise.
    """
    for k, v in data.items():
        if k.lower() == key.lower():
            return v
    return None


def has_case_insensitive(data: dict[str, Any], key: str) -> bool:
    """Check if dict has key (case-insensitive).

    Args:
        data: Dictionary to search.
        key: Key to find (case-insensitive).

    Returns:
        True if key exists, False otherwise.
    """
    for k in data:
        if k.lower() == key.lower():
            return True
    return False


def validate_session_section(session: dict[str, Any], result: ValidationResult) -> None:
    """Validate the session section of the log.

    Args:
        session: The session section data.
        result: ValidationResult to update with errors/warnings.
    """
    # Check required fields
    for field_name in REQUIRED_SESSION_FIELDS:
        if field_name not in session or not session.get(field_name):
            result.errors.append(f"Missing: session.{field_name}")

    # Validate branch pattern
    branch = session.get("branch")
    if branch and not BRANCH_PATTERN.match(branch):
        result.warnings.append(f"Branch '{branch}' doesn't follow conventional naming")

    # Validate commit SHA format
    commit = session.get("startingCommit")
    if commit and not COMMIT_SHA_PATTERN.match(str(commit)):
        result.errors.append(f"Invalid commit SHA format: {commit}")


def validate_must_item(
    check_data: dict[str, Any],
    item_name: str,
    section_name: str,
    result: ValidationResult,
) -> None:
    """Validate a MUST requirement item.

    Args:
        check_data: The check item data.
        item_name: Name of the item being checked.
        section_name: Section name for error messages.
        result: ValidationResult to update with errors/warnings.
    """
    is_complete = get_case_insensitive(check_data, "complete")
    evidence = get_case_insensitive(check_data, "evidence")
    level = get_case_insensitive(check_data, "level")

    if level == "MUST" and not is_complete:
        result.errors.append(f"Incomplete MUST: {section_name}.{item_name}")

    if level == "MUST" and is_complete and not evidence:
        result.warnings.append(f"Missing evidence: {section_name}.{item_name}")


def validate_session_start(session_start: dict[str, Any], result: ValidationResult) -> None:
    """Validate the sessionStart section.

    Args:
        session_start: The sessionStart section data.
        result: ValidationResult to update with errors/warnings.
    """
    for item in SESSION_START_MUST_ITEMS:
        if item in session_start:
            validate_must_item(session_start[item], item, "sessionStart", result)


def validate_session_end(session_end: dict[str, Any], result: ValidationResult) -> None:
    """Validate the sessionEnd section.

    Args:
        session_end: The sessionEnd section data.
        result: ValidationResult to update with errors/warnings.
    """
    for item in SESSION_END_MUST_ITEMS:
        if item in session_end:
            validate_must_item(session_end[item], item, "sessionEnd", result)

    # MUST NOT check: handoffNotUpdated should NOT be complete (HANDOFF.md is read-only)
    if "handoffNotUpdated" in session_end:
        check_data = session_end["handoffNotUpdated"]
        is_complete = get_case_insensitive(check_data, "complete")
        level = get_case_insensitive(check_data, "level")
        if level == "MUST NOT" and is_complete:
            result.errors.append(
                "MUST NOT violated: handoffNotUpdated should be false (HANDOFF.md is read-only)"
            )


def validate_protocol_compliance(
    protocol: dict[str, Any],
    result: ValidationResult,
) -> None:
    """Validate the protocolCompliance section.

    Args:
        protocol: The protocolCompliance section data.
        result: ValidationResult to update with errors/warnings.
    """
    if "sessionStart" in protocol:
        validate_session_start(protocol["sessionStart"], result)
    else:
        result.errors.append("Missing: protocolCompliance.sessionStart")

    if "sessionEnd" in protocol:
        validate_session_end(protocol["sessionEnd"], result)
    else:
        result.errors.append("Missing: protocolCompliance.sessionEnd")


def validate_session_log(data: dict[str, Any]) -> ValidationResult:
    """Validate a session log against the expected schema.

    Args:
        data: Parsed JSON data from session log.

    Returns:
        ValidationResult with errors and warnings.
    """
    result = ValidationResult()

    # Required top-level sections
    if "session" not in data:
        result.errors.append("Missing: session")
    else:
        validate_session_section(data["session"], result)

    if "protocolCompliance" not in data:
        result.errors.append("Missing: protocolCompliance")
    else:
        validate_protocol_compliance(data["protocolCompliance"], result)

    return result


def load_session_file(session_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Load and parse a session log file.

    Args:
        session_path: Path to the session log file.

    Returns:
        Tuple of (parsed data, error message). Data is None if error occurred.
    """
    if not session_path.exists():
        return None, f"Session file not found: {session_path}"

    try:
        content = session_path.read_text(encoding="utf-8")
    except OSError as e:
        return None, f"Could not read session file: {e}"

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in session file: {session_path}"
        error_msg += f"\nSyntax error at line {e.lineno}, position {e.colno}"

        # Show context
        lines = content.split("\n")
        if e.lineno <= len(lines):
            error_msg += f"\nNear: {lines[e.lineno - 1]}"

        error_msg += f"\nError details: {e.msg}"
        error_msg += "\n\nCommon fixes:"
        error_msg += "\n  - Remove trailing commas from arrays/objects"
        error_msg += "\n  - Ensure all strings are properly quoted"
        error_msg += f"\n  - Validate JSON structure with: python -m json.tool '{session_path}'"

        return None, error_msg

    return data, None


def report_results(
    session_path: Path,
    result: ValidationResult,
    pre_commit: bool = False,
) -> None:
    """Report validation results to stdout.

    Args:
        session_path: Path to the session file.
        result: Validation result to report.
        pre_commit: If True, use compact output for pre-commit hook.
    """
    if not pre_commit:
        print()
        print("=== Session Validation ===")
        print(f"File: {session_path}")

    if result.is_valid:
        if not pre_commit:
            print()
            print("[PASS] Session log is valid")
    else:
        if pre_commit:
            print("Session validation FAILED:")
            for error in result.errors:
                print(f"  {error}")
        else:
            print()
            print("[FAIL] Validation errors:")
            for error in result.errors:
                print(f"  - {error}")

    if result.warnings and not pre_commit:
        print()
        print("[WARN] Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "session_path",
        type=Path,
        help="Path to the session log JSON file",
    )
    parser.add_argument(
        "--pre-commit",
        action="store_true",
        help="Suppress verbose output when called from pre-commit hook",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point. Returns exit code.

    Returns:
        0 on success, 1 on validation failure, 2 on unexpected error.
    """
    try:
        args = parse_args()

        # Load session file
        data, error = load_session_file(args.session_path)
        if error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1

        # Validate session log
        result = validate_session_log(data)  # type: ignore[arg-type]

        # Report results
        report_results(args.session_path, result, args.pre_commit)

        return 0 if result.is_valid else 1

    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
