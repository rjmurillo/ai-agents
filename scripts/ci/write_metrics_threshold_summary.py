#!/usr/bin/env python3
"""Write the metrics threshold summary table to GITHUB_STEP_SUMMARY.

Reads CHECK_COVERAGE and CHECK_INFRA_RATE from environment variables and
appends a markdown table with pass/fail status for each metric.
Replaces the "Summary" step in agent-metrics.yml (issue #3531).

EXIT CODES (ADR-035):
  0  - Summary written
  1  - Missing required environment variables
  2  - Usage error
"""

from __future__ import annotations

import os
import sys

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

_COVERAGE_TARGET = 50.0
_INFRA_RATE_TARGET = 100.0


def build_summary(coverage: float, infra_rate: float) -> str:
    """Return markdown for the threshold results table."""
    cov_status = ":white_check_mark:" if coverage >= _COVERAGE_TARGET else ":x:"
    infra_status = ":white_check_mark:" if infra_rate >= _INFRA_RATE_TARGET else ":warning:"

    lines = [
        "## Threshold Check Results",
        "",
        "| Metric | Current | Target | Status |",
        "|--------|---------|--------|--------|",
        f"| Agent Coverage | {coverage}% | {_COVERAGE_TARGET}% | {cov_status} |",
        f"| Infrastructure Review | {infra_rate}% | {_INFRA_RATE_TARGET}% | {infra_status} |",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    coverage_raw = os.environ.get("CHECK_COVERAGE")
    infra_rate_raw = os.environ.get("CHECK_INFRA_RATE")

    if coverage_raw is None or infra_rate_raw is None:
        print("ERROR: CHECK_COVERAGE and CHECK_INFRA_RATE must be set", file=sys.stderr)
        return EXIT_ERROR

    try:
        coverage = float(coverage_raw)
        infra_rate = float(infra_rate_raw)
    except ValueError as exc:
        print(f"ERROR: invalid float value: {exc}", file=sys.stderr)
        return EXIT_ERROR

    summary_text = build_summary(coverage, infra_rate)

    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(summary_text)
    else:
        print(summary_text)

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
