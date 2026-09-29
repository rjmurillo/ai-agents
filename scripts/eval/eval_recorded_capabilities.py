#!/usr/bin/env python3
"""Fold recorded Codex and Copilot session files into the capability matrix.

Reads a capture plan (see `_recorded_captures`), classifies each capture
offline, and emits the #5423 report with `recorded_captures` beside it. It
makes no model call and starts no CLI. A capture from a runtime version other
than the matrix's pinned one is reported and changes no cell.

Exit codes follow AGENTS.md: 0 ok, 2 config, 3 external (output not writable).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from _harness_capability import HarnessCapabilityError, build_report, load_matrix, write_report
from _recorded_captures import apply_verified, derive_captures, load_plan

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

DEFAULT_MATRIX = Path(__file__).parent / "examples" / "harness-capability-matrix.json"
DEFAULT_PLAN = Path(__file__).parent / "examples" / "harness-capability-recorded-captures.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--captures", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path, help="Also write the report here.")
    return parser


def run(matrix: Path, captures: Path) -> dict[str, object]:
    """Build the report with every `VERIFIED` capture applied."""
    records = load_matrix(matrix)
    derived = derive_captures(records, load_plan(captures), captures.parent)
    report: dict[str, object] = build_report(apply_verified(records, derived))
    report["recorded_captures"] = [capture.as_dict() for capture in derived]
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run(args.matrix.resolve(), args.captures.resolve())
        if args.output:
            write_report(args.output.resolve(), report)
    except HarnessCapabilityError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(json.dumps(report, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
