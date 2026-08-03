#!/usr/bin/env python3
"""Run agent drift detection and set GITHUB_OUTPUT drift_detected.

Replaces the inline shell in drift-detection.yml (ADR-006):

    python3 build/scripts/detect_agent_drift.py --output-format text \\
      --fail-on-install-drift || EXIT_CODE=$?
    if [ "${EXIT_CODE:-0}" = "1" ]; then ...

Exit code mapping from detect_agent_drift.py:
  0  - no drift
  1  - drift detected (expected; still exits 0 so the step succeeds)
  2+ - unexpected crash; propagated to the caller

EXIT CODES (ADR-035):
  0 - detection ran; drift_detected output set to true or false
  N>1 - detection script crashed; propagated
"""

from __future__ import annotations

import os
import subprocess
import sys

EXIT_OK = 0


def write_github_output(key: str, value: str) -> None:
    """Append key=value to GITHUB_OUTPUT; fall back to stdout for local runs."""
    path = os.environ.get("GITHUB_OUTPUT", "")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    else:
        print(f"{key}={value}")


def run(_argv: list[str] | None = None) -> int:
    """Run drift detection and set drift_detected output."""
    print("Running agent drift detection...")
    sys.stdout.flush()
    result = subprocess.run(
        [
            sys.executable,
            "build/scripts/detect_agent_drift.py",
            "--output-format",
            "text",
            "--fail-on-install-drift",
        ],
        check=False,
    )
    rc = result.returncode

    if rc == 1:
        write_github_output("drift_detected", "true")
        return EXIT_OK
    if rc == 0:
        write_github_output("drift_detected", "false")
        return EXIT_OK
    # rc >= 2: unexpected error; set false so downstream steps are not confused
    write_github_output("drift_detected", "false")
    return rc


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
