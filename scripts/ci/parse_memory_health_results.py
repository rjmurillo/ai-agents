#!/usr/bin/env python3
"""Parse memory health report results into GitHub Actions step outputs.

Extracted from ``.github/workflows/memory-health.yml`` under ADR-006 (no logic
in workflow YAML). Issue #3541.

The shell this replaces read five ``.summary.*`` fields with five separate
``jq`` calls and derived a ``has_stale`` flag from the stale count. Two
behaviours are load-bearing and preserved exactly:

* A missing report is not a failure. It emits ``has_stale=false`` and
  ``total=0`` and nothing else, so the downstream comment step still runs.
* A stale count that is not an integer (a missing key makes ``jq`` emit
  ``null``) reads as "not stale". In shell, ``[ "null" -gt 0 ]`` errors and
  the ``if`` takes its else branch; the same outcome is produced here rather
  than crashing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SUMMARY_FIELDS = ("total", "healthy", "stale", "exempt", "errors")


def _write_outputs(pairs: list[tuple[str, str]], output_path: str | None) -> None:
    """Append ``key=value`` lines to the GitHub Actions output file."""
    if not output_path:
        for key, value in pairs:
            print(f"{key}={value}")
        return
    with Path(output_path).open("a", encoding="utf-8") as handle:
        for key, value in pairs:
            handle.write(f"{key}={value}\n")


def _is_stale(value: object) -> bool:
    """Report whether a stale count is a positive integer.

    ``jq`` emits ``null`` for a missing key and the shell comparison that
    consumed it failed rather than raising, so anything non-integral is
    treated as "not stale".
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value > 0


def parse_results(results: Path) -> list[tuple[str, str]]:
    """Return the step outputs for a health report, present or not."""
    if not results.is_file():
        return [("has_stale", "false"), ("total", "0")]

    summary = json.loads(results.read_text(encoding="utf-8")).get("summary") or {}
    pairs = [(field, _render(summary.get(field))) for field in _SUMMARY_FIELDS]
    pairs.append(("has_stale", "true" if _is_stale(summary.get("stale")) else "false"))
    return pairs


def _render(value: object) -> str:
    """Render a summary value the way ``jq`` rendered it for the shell."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results",
        default="health-report.json",
        help="Path to the memory health JSON report.",
    )
    args = parser.parse_args(argv)

    results = Path(args.results)
    try:
        pairs = parse_results(results)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"::error::Could not read {results.name}: {exc}")
        return 1

    _write_outputs(pairs, os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
