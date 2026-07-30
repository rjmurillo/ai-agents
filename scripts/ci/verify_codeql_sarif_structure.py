#!/usr/bin/env python3
"""Validate the structure of every SARIF file in a results directory.

Finds all *.sarif files under --results-dir, checks that each has a valid
``version`` and ``runs`` list, and prints a one-line summary per file.
Replaces the inline shell+Python block in test-codeql-integration.yml
(Verify SARIF structure step, issue #3526).

EXIT CODES (ADR-035):
  0  - All SARIF files are structurally valid
  1  - No SARIF files found, or one or more files are invalid
  2  - Usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def validate_sarif(path: Path) -> str | None:
    """Return None if the file is valid, or an error message if it is not."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"JSON parse error in {path}: {exc}"
    if not data.get("version") or not data.get("runs"):
        return f"Invalid SARIF structure in {path}: missing 'version' or 'runs'"
    return None


def validate_sarif_directory(results_dir: Path) -> tuple[bool, list[str]]:
    """Validate all *.sarif files in results_dir.

    Returns (all_valid, list_of_error_messages).
    """
    sarif_files = sorted(results_dir.glob("*.sarif"))
    if not sarif_files:
        return False, [f"ERROR: No SARIF files found in {results_dir}"]

    errors: list[str] = []
    for sarif_file in sarif_files:
        print(f"Validating: {sarif_file.name}")
        error = validate_sarif(sarif_file)
        if error:
            errors.append(error)
        else:
            data = json.loads(sarif_file.read_text(encoding="utf-8"))
            print(f"  Version: {data['version']}")
            print(f"  Runs: {len(data['runs'])}")
            print(f"  Results: {len(data['runs'][0]['results'])}")

    return not errors, errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        default=".codeql/results",
        help="Directory containing SARIF files (default: .codeql/results)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results_dir = Path(args.results_dir)
    all_valid, errors = validate_sarif_directory(results_dir)
    for err in errors:
        print(err, file=sys.stderr)
    return EXIT_OK if all_valid else EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
