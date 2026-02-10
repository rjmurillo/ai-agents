#!/usr/bin/env python3
"""Aggregate session protocol validation verdicts across all validated files.

Replaces the inline PowerShell block in the 'Aggregate Verdicts'
step (id: aggregate) of ai-session-protocol.yml.

Input env vars:
    GITHUB_OUTPUT      - Path to GitHub Actions output file
    GITHUB_WORKSPACE   - Workspace root (for package imports)
"""

from __future__ import annotations

import os
import re
import sys
from glob import glob

# Add workspace root to Python path for package imports
workspace = os.environ.get("GITHUB_WORKSPACE", ".")
sys.path.insert(0, workspace)

from scripts.ai_review_common import write_log  # noqa: E402


def write_output(key: str, value: str) -> None:
    """Append a key=value line to the GitHub Actions output file."""
    output_file = os.environ.get("GITHUB_OUTPUT", "")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def main() -> None:
    overall_verdict = "PASS"
    total_must_failures = 0

    # Process all verdict files
    verdict_files = sorted(glob("validation-results/*-verdict.txt"))

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

    # Count MUST failures
    must_files = sorted(glob("validation-results/*-must-failures.txt"))
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


if __name__ == "__main__":
    main()
