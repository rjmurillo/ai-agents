#!/usr/bin/env python3
"""Run the hook-bypass detector and enforce its three-way exit contract.

Replaces the inline shell block in `.github/workflows/audit-hook-bypass.yml`,
which disabled `set -e`, captured `$?`, then re-derived the contract with two
tests. Keeping the contract here (ADR-006: no logic in YAML) makes the crash
path testable, which is the path Issue #2808 showed was silently masked.

`scripts/detect_hook_bypass.py` exit contract:

  0  - clean, no bypass indicators
  1  - indicators found; the audit is advisory and must not fail the job
  >=2 - the detector itself failed and produced no trustworthy result

A detector crash must not be reported as "0 indicators". This script forwards
any code >= 2 unchanged, and additionally fails when the detector returned a
non-crash code but wrote no report, which is the same broken-audit condition
reached by a different route.

EXIT CODES (ADR-035):
  0  - Success: the detector ran; 0 or more indicators recorded
  1  - Error: the detector produced no usable report
  2+ - Error: forwarded from the detector's own crash code
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_NO_REPORT = 1
DETECTOR_CRASH_FLOOR = 2


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the audit runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--detector", required=True, help="Path to detect_hook_bypass.py."
    )
    parser.add_argument("--base-ref", required=True, help="Base ref to audit against.")
    parser.add_argument("--output", required=True, help="Path for the audit JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the detector and enforce its exit contract. Returns an ADR-035 code."""
    args = build_parser().parse_args(argv)

    try:
        result = subprocess.run(
            [
                sys.executable,
                args.detector,
                "--base-ref",
                args.base_ref,
                "--output",
                args.output,
            ],
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        print(f"::error::cannot run {args.detector}: {exc}", file=sys.stderr)
        return EXIT_NO_REPORT

    if result.returncode >= DETECTOR_CRASH_FLOOR:
        print(
            f"::error::detect_hook_bypass.py failed to run (exit {result.returncode})"
        )
        return result.returncode

    report = Path(args.output)
    if not report.is_file() or report.stat().st_size == 0:
        print(f"::error::audit report missing or empty: {report}")
        return EXIT_NO_REPORT

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
