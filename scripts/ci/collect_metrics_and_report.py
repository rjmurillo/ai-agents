#!/usr/bin/env python3
"""Collect agent metrics and write a report and step summary.

Runs .claude/skills/metrics/collect_metrics.py, saves output to
metrics-report.txt, and appends to GITHUB_STEP_SUMMARY.
Replaces the "Collect metrics" step in agent-metrics.yml (issue #3531).

EXIT CODES (ADR-035):
  0  - Metrics collected and report written
  1  - collect_metrics.py failed
  2  - Usage error
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

_COLLECT_SCRIPT = ".claude/skills/metrics/collect_metrics.py"
_REPORT_FILE = "metrics-report.txt"


def collect_metrics(since: str, output_format: str, report_path: Path) -> bool:
    """Run collect_metrics.py and write to report_path. Return True on success."""
    result = subprocess.run(
        [sys.executable, _COLLECT_SCRIPT, "--since", since, "--output", output_format],
        capture_output=True,
        text=True,
        check=False,
    )
    report_path.write_text(result.stdout, encoding="utf-8")
    return result.returncode == 0


def write_step_summary(report_path: Path, output_format: str, summary_file: str) -> None:
    """Append metrics report to GITHUB_STEP_SUMMARY."""
    content = report_path.read_text(encoding="utf-8")
    with open(summary_file, "a", encoding="utf-8") as f:
        f.write("## Agent Metrics Summary\n\n")
        if output_format == "json":
            f.write("```json\n")
            f.write(content)
            f.write("```\n")
        else:
            f.write(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        default=os.environ.get("PERIOD_DAYS", "7"),
        help="Number of days to analyze (default: $PERIOD_DAYS or 7)",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        default=os.environ.get("PERIOD_FORMAT", "markdown"),
        help="Output format: markdown|json|summary (default: $PERIOD_FORMAT or markdown)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = Path(_REPORT_FILE)

    if not collect_metrics(args.since, args.output_format, report_path):
        print("ERROR: collect_metrics.py failed", file=sys.stderr)
        return EXIT_ERROR

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        write_step_summary(report_path, args.output_format, summary_file)

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
