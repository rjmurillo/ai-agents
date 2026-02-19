#!/usr/bin/env python3
"""Aggregate session protocol validation verdicts across all validated files.

Input env vars (used as defaults for CLI args):
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from glob import glob

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import write_log, write_output  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Aggregate session protocol validation verdicts across all validated files.",
    )
    parser.add_argument(
        "--results-dir",
        default="validation-results",
        help="Directory containing verdict and must-failures files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results_dir = os.path.abspath(args.results_dir)
    overall_verdict = "PASS"
    total_must_failures = 0

    verdict_files = sorted(glob(f"{results_dir}/*-verdict.txt"))

    if not verdict_files:
        write_log("WARNING: No verdict files found in validation-results/")
        print(
            "::warning::No session verdict files found. Validation may not have run.",
            file=sys.stderr,
        )
        overall_verdict = "WARN"

    for verdict_file in verdict_files:
        filename = os.path.basename(verdict_file)
        with open(verdict_file, encoding="utf-8") as f:
            verdict = f.read().strip()

        write_log(f"Found verdict: {verdict} from {filename}")

        if verdict in ("CRITICAL_FAIL", "REJECTED", "NON_COMPLIANT"):
            overall_verdict = "CRITICAL_FAIL"
        elif verdict == "WARN" and overall_verdict == "PASS":
            overall_verdict = "WARN"

    must_files = sorted(glob(f"{results_dir}/*-must-failures.txt"))
    for must_file in must_files:
        with open(must_file, encoding="utf-8") as f:
            content = f.read().strip()

        match = re.match(r"^(\d+)", content)
        if match:
            total_must_failures += int(match.group(1))

    if total_must_failures > 0:
        overall_verdict = "CRITICAL_FAIL"

    write_output("final_verdict", overall_verdict)
    write_output("must_failures", str(total_must_failures))

    write_log(f"Final verdict: {overall_verdict} (MUST failures: {total_must_failures})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
