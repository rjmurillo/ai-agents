#!/usr/bin/env python3
"""Summarize memory-validation results into workflow outputs.

Replaces the inline `jq` block in `.github/workflows/memory-validation.yml`,
which counted entries, counted stale entries, derived the valid count with
shell arithmetic, and wrote four `GITHUB_OUTPUT` lines. Keeping the counting
here (ADR-006: no logic in YAML) makes the crashed-verify path testable, which
is the path Issue #2808 showed was reported as a green Pass.

An entry is stale when its `valid` field is exactly boolean `false`. That
matches the `jq 'select(.valid == false)'` this replaces: a missing or null
`valid` is not `false`, so it is not counted stale. Preserving the comparison
keeps the reported numbers identical across the extraction.

A missing or empty results file means the verify step crashed. That is an
error, not a zero-entry pass.

EXIT CODES (ADR-035):
  0  - Success: counts written to GITHUB_OUTPUT
  1  - Error: results missing, empty, or not a JSON array
  2  - Error: usage/configuration (no GITHUB_OUTPUT destination)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_NO_RESULTS = 1
EXIT_USAGE = 2


def counts(entries: list[object]) -> tuple[int, int, int]:
    """Return (total, valid, stale) for a parsed results array."""
    stale = sum(
        1 for e in entries if isinstance(e, dict) and e.get("valid", None) is False
    )
    total = len(entries)
    return total, total - stale, stale


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the results summarizer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, help="Path to memory-validation-results.json."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Destination for key=value lines. Defaults to $GITHUB_OUTPUT.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write total/valid/stale/has_stale outputs. Returns an ADR-035 code."""
    args = build_parser().parse_args(argv)

    destination = args.output or os.environ.get("GITHUB_OUTPUT")
    if not destination:
        print("ERROR: no --output and no GITHUB_OUTPUT set", file=sys.stderr)
        return EXIT_USAGE

    results = Path(args.input)
    if not results.is_file() or results.stat().st_size == 0:
        print(
            f"::error::{results.name} missing or empty (verify-all likely crashed)"
        )
        return EXIT_NO_RESULTS

    try:
        entries = json.loads(results.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"::error::cannot parse {results}: {exc}")
        return EXIT_NO_RESULTS

    if not isinstance(entries, list):
        print(f"::error::{results} is not a JSON array")
        return EXIT_NO_RESULTS

    total, valid, stale = counts(entries)
    lines = [
        f"total={total}",
        f"valid={valid}",
        f"stale={stale}",
        f"has_stale={'true' if stale > 0 else 'false'}",
    ]
    with open(destination, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
