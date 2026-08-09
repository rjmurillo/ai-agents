#!/usr/bin/env python3
"""Decide whether Session Protocol Results should aggregate or fail."""

from __future__ import annotations

import os
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
_VALID_DETECT_RESULTS = frozenset({"success", "skipped"})


def decide(
    check_changes_result: str,
    detect_changes_result: str,
    has_sessions: str,
) -> tuple[int, bool, str]:
    """Return exit code, skip flag, and diagnostic message."""
    if check_changes_result != "success":
        return EXIT_LOGIC, False, "Session change detection prerequisite failed"
    if detect_changes_result not in _VALID_DETECT_RESULTS:
        return EXIT_LOGIC, False, "Changed-session detection failed"
    if detect_changes_result == "skipped" or has_sessions == "false":
        return EXIT_OK, True, "Skipped - no session file changes detected"
    if has_sessions == "true":
        return EXIT_OK, False, "Session validation artifacts require aggregation"
    return EXIT_LOGIC, False, "Changed-session detection produced no decision"


def main() -> int:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG

    exit_code, skip, message = decide(
        os.environ.get("CHECK_CHANGES_RESULT", ""),
        os.environ.get("DETECT_CHANGES_RESULT", ""),
        os.environ.get("HAS_SESSIONS", ""),
    )
    print(message)
    if exit_code != EXIT_OK:
        print(f"::error::{message}", file=sys.stderr)
        return exit_code

    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"skip={str(skip).lower()}\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
