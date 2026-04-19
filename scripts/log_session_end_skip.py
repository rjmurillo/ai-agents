#!/usr/bin/env python3
"""Log session-end skip events for compliance observability.

When an agent closes a session without running the session-end skill, invoke
this script to append a structured event to the skip log. The log is consumed
by the retrospective agent to track compliance drift over time.

Skipping session-end is a protocol violation. Logging the skip does not
authorize it, it only preserves evidence so the failure can be measured.

Usage:
    python3 log_session_end_skip.py --reason "agent timed out before session-end"
    python3 log_session_end_skip.py --reason "abandoned mid-task" --session-id S-123
    python3 log_session_end_skip.py --reason "..." --log-path custom/skips.jsonl

Exit codes (ADR-035):
    0  Skip logged successfully
    2  Invalid arguments (empty reason, etc.)
    3  I/O failure writing the skip log
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_LOG_PATH = Path(".agents/sessions/session-end-skips.jsonl")


def build_event(reason: str, session_id: str | None = None) -> dict[str, str]:
    """Build the skip event payload."""
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": "session_closed_without_session_end",
        "sessionId": session_id or os.getenv("OPENCLAW_SESSION_ID", "unknown"),
        "reason": reason,
    }


def append_event(event: dict[str, str], log_path: Path) -> None:
    """Append event as a single JSONL line, creating parent dirs if needed."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        json.dump(event, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record a session-end skip event for compliance tracking.",
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="Human-readable explanation for why session-end was not run.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session identifier. Falls back to OPENCLAW_SESSION_ID or 'unknown'.",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help=f"Path to the skip log. Default: {DEFAULT_LOG_PATH}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    reason = args.reason.strip()
    if not reason:
        print("error: --reason must be non-empty", file=sys.stderr)
        return 2

    event = build_event(reason=reason, session_id=args.session_id)
    try:
        append_event(event, args.log_path)
    except OSError as exc:
        print(f"error: could not write skip log: {exc}", file=sys.stderr)
        return 3

    print(f"logged session-end skip to {args.log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
