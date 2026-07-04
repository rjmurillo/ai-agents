#!/usr/bin/env python3
"""Parse hook-bypass audit JSON into the indicator count the audit workflow reads.

This is the parse half of `.github/workflows/audit-hook-bypass.yml`. The workflow
runs `scripts/detect_hook_bypass.py --output <json>`, then calls this script to
extract the bypass-indicator count. Keeping the logic here (ADR-006: no logic in
YAML) lets it be tested; it replaces an inline `python3 -c` heredoc that read the
JSON and counted `bypass_indicators` directly in the workflow step.

Canonical source it mirrors: `scripts/detect_hook_bypass.py`, dataclass
`AuditReport` (serialized via `dataclasses.asdict`). The only field this script
reads is `bypass_indicators` (a list); the count is its length.

    {
        "timestamp": <str>,
        "branch": <str>,
        "base_ref": <str>,
        "total_commits": <int>,
        "bypass_indicators": [ {...}, ... ]
    }

EXIT CODES (ADR-035):
  0  - Success: count written
  1  - Error: malformed input (bad JSON, missing/!list bypass_indicators)
  2  - Error: usage/configuration (file not found, bad argument)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_MALFORMED = 1
EXIT_USAGE = 2


def _indicator_count(data: object) -> int:
    """Return the number of bypass indicators in a parsed audit report."""
    if not isinstance(data, dict):
        raise ValueError("audit report is not a JSON object")
    indicators = data.get("bypass_indicators")
    if not isinstance(indicators, list):
        raise ValueError("'bypass_indicators' is missing or not a list")
    return len(indicators)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the audit-result parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the hook-bypass audit JSON written by detect_hook_bypass.py.",
    )
    parser.add_argument(
        "--count-out",
        required=True,
        help="Path to write the bare indicator count (integer) to.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse audit JSON and write the indicator count. Returns an ADR-035 code."""
    args = build_parser().parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        return EXIT_USAGE

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read input {input_path}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except UnicodeDecodeError as exc:
        print(f"ERROR: malformed UTF-8 in {input_path}: {exc}", file=sys.stderr)
        return EXIT_MALFORMED
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed JSON in {input_path}: {exc}", file=sys.stderr)
        return EXIT_MALFORMED

    try:
        count = _indicator_count(data)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_MALFORMED

    Path(args.count_out).write_text(f"{count}\n", encoding="utf-8")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
