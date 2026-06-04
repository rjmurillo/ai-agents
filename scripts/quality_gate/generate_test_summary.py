#!/usr/bin/env python3
"""Generate a Markdown summary of pre-executed test results for the QA agent.

Extracted from the inline ``Generate test summary`` step in
``.github/workflows/ai-pr-quality-gate.yml`` (ADR-006: no logic in YAML).

The QA agent runs via Copilot CLI (text-in/text-out) with no shell access, so
the workflow executes pytest first and passes the formatted summary as agent
context. This script reproduces the original inline block exactly: it reads the
pytest status and summary from the environment and writes a ``test_summary``
multiline value to ``GITHUB_OUTPUT`` using a randomized heredoc delimiter.

Input env vars:
    PYTEST_STATUS   - pytest outcome (PASS/FAIL/ERROR/SKIPPED). Default SKIPPED.
    PYTEST_SUMMARY  - one-line pytest summary. Default 'Not executed'.
    GITHUB_OUTPUT   - path to the GitHub Actions output file.

Exit codes (ADR-035):
    0 - summary written successfully
    2 - GITHUB_OUTPUT is not set (config error)
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path


def build_summary(pytest_status: str, pytest_summary: str) -> str:
    """Return the Markdown test-result summary for the QA agent context."""

    summary = "## Pre-executed Test Results\n\n"
    summary += "### pytest (Python)\n"
    summary += f"- **Status**: {pytest_status}\n"
    summary += f"- **Summary**: {pytest_summary}\n"
    return summary


def write_summary(output_path: Path, summary: str) -> None:
    """Append a ``test_summary`` multiline output using a heredoc delimiter."""

    delimiter = f"EOF_SUMMARY_{random.randint(1000, 9999)}"
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"test_summary<<{delimiter}\n")
        handle.write(summary)
        handle.write(f"{delimiter}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--pytest-status",
        default=os.environ.get("PYTEST_STATUS", "SKIPPED"),
        help="pytest outcome (PASS/FAIL/ERROR/SKIPPED).",
    )
    parser.add_argument(
        "--pytest-summary",
        default=os.environ.get("PYTEST_SUMMARY", "Not executed"),
        help="One-line pytest summary text.",
    )
    args = parser.parse_args(argv)

    summary = build_summary(args.pytest_status, args.pytest_summary)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        print("error: GITHUB_OUTPUT is not set", file=sys.stderr)
        return 2

    write_summary(Path(github_output), summary)

    print("Generated test summary:")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
