#!/usr/bin/env python3
"""Inject stricter protocol enforcement for autonomy keywords.

Claude Code UserPromptSubmit hook that detects keywords signaling
autonomous execution (e.g., "autonomous", "hands-off", "without asking").

When detected, injects stricter protocol guards into context.

Hook Type: UserPromptSubmit
Exit Codes (Claude Hook Semantics, exempt from ADR-035):
    0 = Always (educational injection, not blocking)
"""

from __future__ import annotations

import json
import re
import sys

# Keywords signaling autonomous/unattended execution
AUTONOMY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bautonomous\b", re.IGNORECASE),
    re.compile(r"\bhands-off\b", re.IGNORECASE),
    re.compile(r"\bwithout asking\b", re.IGNORECASE),
    re.compile(r"\bwithout confirmation\b", re.IGNORECASE),
    re.compile(r"\bauto-\w+", re.IGNORECASE),
    re.compile(r"\bunattended\b", re.IGNORECASE),
    re.compile(r"\brun autonomously\b", re.IGNORECASE),
    re.compile(r"\bfull autonomy\b", re.IGNORECASE),
    re.compile(r"\bno human\b", re.IGNORECASE),
    re.compile(r"\bno verification\b", re.IGNORECASE),
    re.compile(r"\bblindly\b", re.IGNORECASE),
]

STRICTER_PROTOCOL_MESSAGE = (
    "\nAutonomous mode: Stricter protocol active. "
    "Session log with evidence required. "
    "High-risk ops (merge, force-push, branch delete) need consensus gates "
    "via /orchestrator. Blocked on main. See SESSION-PROTOCOL.md.\n"
)


def has_autonomy_keywords(prompt: str) -> bool:
    """Check if the prompt contains any autonomy-signaling keywords."""
    if not prompt or not prompt.strip():
        return False
    for pattern in AUTONOMY_PATTERNS:
        if pattern.search(prompt):
            return True
    return False


def extract_prompt(hook_input: dict[str, object]) -> str | None:
    """Extract user prompt from hook input with fallback for schema variations."""
    for key in ("prompt", "user_message_text", "message"):
        value = hook_input.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def main() -> int:
    """Main hook entry point. Returns exit code."""
    try:
        if sys.stdin.isatty():
            return 0

        input_json = sys.stdin.read()
        if not input_json.strip():
            return 0

        hook_input = json.loads(input_json)
    except (json.JSONDecodeError, ValueError):
        return 0

    user_prompt = extract_prompt(hook_input)
    if not user_prompt:
        return 0

    if has_autonomy_keywords(user_prompt):
        print(STRICTER_PROTOCOL_MESSAGE)

    return 0


if __name__ == "__main__":
    sys.exit(main())
