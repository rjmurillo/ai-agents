#!/usr/bin/env python3
"""Report smoke matrix results (pass-through gate).

Replaces the bash 'Report' block in the smoke-result job of
cli-smoke.yml (ADR-006).

ENV:
  CHECK_PATHS_RESULT - result of check-paths job
  CLI_CHANGED        - whether CLI files changed ("true" / "false")
  SMOKE_RESULT       - result of smoke matrix job
  VERIFY_RESULT      - result of typecheck/unit tests job

EXIT CODES (ADR-035):
  0 - all required jobs passed (or CLI unchanged)
  1 - one or more required jobs failed
"""

from __future__ import annotations

import os
import sys


def run(_argv: list[str] | None = None) -> int:
    """Validate smoke matrix results and report."""
    check_paths_result = os.environ.get("CHECK_PATHS_RESULT", "")
    cli_changed = os.environ.get("CLI_CHANGED", "")
    smoke_result = os.environ.get("SMOKE_RESULT", "")
    verify_result = os.environ.get("VERIFY_RESULT", "")

    if check_paths_result != "success":
        print(f"::error::Check changed paths result: {check_paths_result}")
        return 1

    if cli_changed != "true":
        print("No CLI files changed - smoke matrix skipped.")
        return 0

    if smoke_result != "success":
        print(f"::error::Smoke matrix result: {smoke_result}")
        return 1

    if verify_result != "success":
        print(f"::error::Typecheck and unit tests result: {verify_result}")
        return 1

    print("Smoke matrix passed on all 6 jobs; typecheck and unit tests passed.")
    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
