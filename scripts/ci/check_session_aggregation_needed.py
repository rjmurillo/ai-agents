#!/usr/bin/env python3
"""Decide whether Session Protocol Results should aggregate or fail."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2


def decide(
    check_changes_result: str,
    should_run_protocol: str,
    detect_changes_result: str,
    has_sessions: str,
    validate_result: str,
    session_files: str,
) -> tuple[int, bool, int, str]:
    """Return exit code, skip flag, and diagnostic message."""
    if check_changes_result != "success":
        return EXIT_LOGIC, False, 0, "Session change detection prerequisite failed"
    if should_run_protocol == "false":
        return EXIT_OK, True, 0, "Skipped - no session file changes detected"
    if should_run_protocol != "true":
        return EXIT_LOGIC, False, 0, "Session path filter produced no decision"
    if detect_changes_result != "success":
        return EXIT_LOGIC, False, 0, "Changed-session detection failed"
    if has_sessions == "false":
        return EXIT_OK, True, 0, "Skipped - no session file changes detected"
    if has_sessions == "true":
        if validate_result != "success":
            return EXIT_LOGIC, False, 0, "Session validation matrix failed"
        try:
            sessions = json.loads(session_files)
        except json.JSONDecodeError:
            return EXIT_LOGIC, False, 0, "Session file matrix is invalid JSON"
        if not isinstance(sessions, list) or not sessions:
            return EXIT_LOGIC, False, 0, "Session file matrix is empty or invalid"
        return (
            EXIT_OK,
            False,
            len(sessions),
            "Session validation artifacts require aggregation",
        )
    return EXIT_LOGIC, False, 0, "Changed-session detection produced no decision"


def main() -> int:
    output_path = os.environ.get("GITHUB_OUTPUT", "")
    if not output_path:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG

    exit_code, skip, expected_results, message = decide(
        os.environ.get("CHECK_CHANGES_RESULT", ""),
        os.environ.get("SHOULD_RUN_PROTOCOL", ""),
        os.environ.get("DETECT_CHANGES_RESULT", ""),
        os.environ.get("HAS_SESSIONS", ""),
        os.environ.get("VALIDATE_RESULT", ""),
        os.environ.get("SESSION_FILES", ""),
    )
    print(message)
    if exit_code != EXIT_OK:
        print(f"::error::{message}", file=sys.stderr)
        return exit_code

    with Path(output_path).open("a", encoding="utf-8") as output:
        output.write(f"skip={str(skip).lower()}\n")
        output.write(f"expected_results={expected_results}\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
