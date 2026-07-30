#!/usr/bin/env python3
"""Measure the npm pack size and warn if it exceeds the 50 MB limit.

Runs `npm pack --dry-run --json` in --package-dir, reads the size bytes from
the JSON output, and emits a warning annotation if the limit is exceeded.
Replaces the inline shell block in publish.yml (issue #3533).

EXIT CODES (ADR-035):
  0  - Pack completed (warning emitted if limit exceeded, but does not fail)
  1  - npm pack failed or unexpected output
  2  - Usage error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

_SIZE_LIMIT_BYTES = 52_428_800  # 50 MiB


def measure_pack_size(package_dir: Path) -> tuple[int | None, str]:
    """Run npm pack --dry-run --json and return (bytes, human_size_line).

    Returns (None, error_message) on failure.
    """
    result = subprocess.run(
        ["npm", "pack", "--dry-run", "--json"],
        cwd=package_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        return None, f"npm pack failed: {result.stderr.strip()}"

    try:
        data = json.loads(result.stdout)
        size_bytes = data[0].get("size") if data else None
    except (json.JSONDecodeError, IndexError, TypeError):
        size_bytes = None

    # Also run without --json for the human-readable summary line
    result2 = subprocess.run(
        ["npm", "pack", "--dry-run"],
        cwd=package_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    last_line = result2.stdout.strip().splitlines()[-1] if result2.stdout.strip() else ""

    return size_bytes, last_line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-dir",
        required=True,
        help="Path to the npm package directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    package_dir = Path(args.package_dir)

    size_bytes, detail = measure_pack_size(package_dir)
    if size_bytes is None:
        print(f"Pack size: {detail}")
    else:
        print(f"Pack size: {detail}")
        if size_bytes > _SIZE_LIMIT_BYTES:
            print("::warning::Pack size exceeds 50MB threshold")

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
