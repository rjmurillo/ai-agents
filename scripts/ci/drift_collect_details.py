#!/usr/bin/env python3
"""Collect drift details: re-run detection with JSON output, parse results.

Replaces the inline shell in drift-detection.yml (ADR-006):

    set +e
    python3 build/scripts/detect_agent_drift.py --output-format json > drift-results.json
    rc=$?
    if [ "$rc" -ge 2 ]; then ...

Writes drift-results.json, calls parse_drift_results.py, then writes
agents_count to GITHUB_OUTPUT.

ENV:
  RUNNER_TEMP  - directory for intermediate files (defaults to ".")

EXIT CODES (ADR-035):
  0 - details collected and agents_count output set
  1 - empty JSON or parse error
  N - detection crashed (exit N from detect_agent_drift.py)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_ERR = 1


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout for local runs."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def run(_argv: list[str] | None = None) -> int:
    """Collect drift details and set agents_count output."""
    runner_temp = os.environ.get("RUNNER_TEMP", ".")

    # Re-run drift detection with JSON output.
    with open("drift-results.json", "w", encoding="utf-8") as fh:
        result = subprocess.run(
            [
                sys.executable,
                "build/scripts/detect_agent_drift.py",
                "--output-format",
                "json",
            ],
            stdout=fh,
            check=False,
        )

    rc = result.returncode
    if rc >= 2:
        print(f"::error::drift detection crashed on re-run (exit {rc})")
        return rc

    # Validate non-empty JSON output.
    json_path = Path("drift-results.json")
    if not json_path.exists() or json_path.stat().st_size == 0:
        print("::error::drift-results.json is empty after re-run")
        return EXIT_ERR

    # Parse results via the dedicated script.
    details_out = Path(runner_temp) / "drift-details.md"
    count_out = Path("drift-count.txt")
    result2 = subprocess.run(
        [
            sys.executable,
            "scripts/ci/parse_drift_results.py",
            "--input",
            str(json_path),
            "--details-out",
            str(details_out),
            "--count-out",
            str(count_out),
        ],
        check=False,
    )
    if result2.returncode != 0:
        return result2.returncode

    # Read the agent count and publish it.
    agents_count = count_out.read_text(encoding="utf-8").strip()
    write_github_output("agents_count", agents_count)
    return EXIT_OK


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
