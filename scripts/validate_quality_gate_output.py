#!/usr/bin/env python3
"""Validate PR quality gate output against JSON schema.

Validates that agent output conforms to the standardized schema defined in
.agents/schemas/pr-quality-gate-output.schema.json.

EXIT CODES:
  0  - Success: Output is valid
  1  - Error: Output validation failed
  2  - Error: Configuration or unexpected error

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
_SCHEMA_PATH = _PROJECT_ROOT / ".agents" / "schemas" / "pr-quality-gate-output.schema.json"

VALID_VERDICTS = frozenset({"PASS", "WARN", "CRITICAL_FAIL"})
VALID_AGENTS = frozenset({"security", "qa", "analyst", "architect", "devops", "roadmap"})
VALID_SEVERITIES = frozenset({"critical", "high", "medium", "low"})
REQUIRED_FIELDS = frozenset({"verdict", "message", "agent", "timestamp", "findings"})
REQUIRED_FINDING_FIELDS = frozenset({"severity", "category", "description"})


def validate_output(data: dict) -> list[str]:
    """Validate quality gate output against schema rules.

    Returns a list of error messages. Empty list means valid.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["Root element must be a JSON object"]

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        errors.append(f"Missing required fields: {', '.join(sorted(missing))}")
        return errors

    if data["verdict"] not in VALID_VERDICTS:
        errors.append(
            f"Invalid verdict '{data['verdict']}'. "
            f"Must be one of: {', '.join(sorted(VALID_VERDICTS))}"
        )

    if not isinstance(data["message"], str) or not data["message"].strip():
        errors.append("'message' must be a non-empty string")

    if data["agent"] not in VALID_AGENTS:
        errors.append(
            f"Invalid agent '{data['agent']}'. "
            f"Must be one of: {', '.join(sorted(VALID_AGENTS))}"
        )

    if not isinstance(data["timestamp"], str) or not data["timestamp"].strip():
        errors.append("'timestamp' must be a non-empty string")

    if not isinstance(data["findings"], list):
        errors.append("'findings' must be an array")
    else:
        for i, finding in enumerate(data["findings"]):
            if not isinstance(finding, dict):
                errors.append(f"findings[{i}]: must be an object")
                continue
            f_missing = REQUIRED_FINDING_FIELDS - set(finding.keys())
            if f_missing:
                errors.append(
                    f"findings[{i}]: missing required fields: "
                    f"{', '.join(sorted(f_missing))}"
                )
            if "severity" in finding and finding["severity"] not in VALID_SEVERITIES:
                errors.append(
                    f"findings[{i}]: invalid severity '{finding['severity']}'"
                )
            if "cwe" in finding:
                cwe = finding["cwe"]
                if not isinstance(cwe, str) or not re.fullmatch(r"CWE-\d+", cwe):
                    errors.append(
                        f"findings[{i}]: 'cwe' must match pattern CWE-NNN"
                    )

    return errors


def main() -> int:
    """Parse arguments and validate the provided JSON file."""
    parser = argparse.ArgumentParser(
        description="Validate PR quality gate output against schema"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to JSON file containing quality gate output",
    )
    args = parser.parse_args()

    input_path: Path = args.input_file
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 2

    try:
        with open(input_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 1

    errors = validate_output(data)
    if errors:
        print(f"Validation failed with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"Valid: {data['agent']} agent output ({data['verdict']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
