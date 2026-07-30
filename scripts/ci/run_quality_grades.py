#!/usr/bin/env python3
"""Run the quality-grades grader in both output formats and post the summary.

Replaces the inline shell block in `.github/workflows/quality-grades.yml`,
which validated the `top_n` input with a bash regex, built an optional flag
string, invoked the grader twice, then appended the markdown report to the job
summary. Keeping the validation and the flag assembly here (ADR-006: no logic
in YAML) makes both testable, and passing the flag as a real argv element
removes the unquoted `$TOP_N_FLAG` word-splitting the shell relied on.

`top_n` is optional. An empty value and the literal `0` both mean "no limit"
and produce no flag. Any other value must be a non-negative decimal integer.

The grader path is supplied by the caller rather than hardcoded so this script
carries no dependency on the skills tree layout.

EXIT CODES (ADR-035):
  0  - Success: both reports written and the summary appended
  1  - Error: the grader failed
  2  - Error: usage/configuration (non-numeric top_n, grader not found)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

EXIT_SUCCESS = 0
EXIT_GRADER_FAILED = 1
EXIT_USAGE = 2

SUMMARY_HEADING = "## Quality Grades Report"


def top_n_flag(raw: str) -> list[str]:
    """Return the `--top-n` argv fragment for a raw workflow input.

    Empty and `0` mean unlimited and yield no flag. Raises ValueError when the
    value is present but not a non-negative decimal integer.
    """
    value = raw.strip()
    if value in ("", "0"):
        return []
    if not value.isdecimal():
        raise ValueError("top_n must be numeric")
    return ["--top-n", value]


def _grade(grader: str, fmt: str, flag: list[str], destination: Path) -> int:
    """Run the grader for one format, writing stdout to destination."""
    result = subprocess.run(
        [sys.executable, grader, "--format", fmt, *flag],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(f"ERROR: grader failed for --format {fmt}:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return result.returncode
    destination.write_text(result.stdout, encoding="utf-8")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the quality-grades runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grader", required=True, help="Path to grade_domains.py.")
    parser.add_argument("--json-out", required=True, help="Path for the JSON report.")
    parser.add_argument(
        "--markdown-out", required=True, help="Path for the markdown report."
    )
    parser.add_argument(
        "--top-n", default="", help="Raw workflow input; empty or 0 means unlimited."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Grade in both formats and append the markdown to the job summary."""
    args = build_parser().parse_args(argv)

    try:
        flag = top_n_flag(args.top_n)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if not Path(args.grader).is_file():
        print(f"ERROR: grader not found: {args.grader}", file=sys.stderr)
        return EXIT_USAGE

    markdown = Path(args.markdown_out)
    for fmt, destination in (("json", Path(args.json_out)), ("markdown", markdown)):
        if _grade(args.grader, fmt, flag, destination) != 0:
            return EXIT_GRADER_FAILED

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        report = markdown.read_text(encoding="utf-8")
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"{SUMMARY_HEADING}\n\n{report}")
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
