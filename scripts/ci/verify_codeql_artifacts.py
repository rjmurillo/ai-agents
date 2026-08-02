#!/usr/bin/env python3
"""Verify CodeQL scan artifacts exist after a scan run.

Checks that the database directory and SARIF output file were created for the
given language. Replaces the inline shell block in test-codeql-integration.yml
(Verify scan artifacts step, issue #3526).

EXIT CODES (ADR-035):
  0  - All artifacts present
  1  - One or more artifacts missing
  2  - Usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_MISSING = 1
EXIT_USAGE = 2


def check_artifacts(
    language: str,
    db_base: str = ".codeql/db",
    results_base: str = ".codeql/results",
) -> list[str]:
    """Return a list of error messages; empty means all artifacts present."""
    errors: list[str] = []

    db_path = Path(db_base) / language
    if not db_path.is_dir():
        errors.append(f"ERROR: Database not created: {db_path}")
    else:
        print(f"Database created: {db_path}")

    sarif_path = Path(results_base) / f"{language}.sarif"
    if not sarif_path.is_file():
        errors.append(f"ERROR: SARIF not created: {sarif_path}")
    else:
        try:
            data = json.loads(sarif_path.read_text(encoding="utf-8"))
            findings = len(data["runs"][0]["results"])
            print(f"SARIF created: {findings} findings")
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            errors.append(f"ERROR: Cannot parse SARIF at {sarif_path}: {exc}")

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", required=True, help="CodeQL language name")
    parser.add_argument("--db-base", default=".codeql/db")
    parser.add_argument("--results-base", default=".codeql/results")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = check_artifacts(args.language, args.db_base, args.results_base)
    for err in errors:
        print(err)
    return EXIT_MISSING if errors else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
