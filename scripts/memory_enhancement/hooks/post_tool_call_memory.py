#!/usr/bin/env python3
"""Hook: PostToolUseFailure - Capture learnable failures from tool results.

Analyzes tool output for an error worth remembering and suggests a memory
for it. Governed mode: emits structured ``additionalContext`` JSON on stdout
so the host can surface the suggestion without polluting stderr.
"""

from __future__ import annotations

import json
import sys

from ..extraction import (
    extract_error_pattern,
    format_suggestion,
)


def main() -> int:
    """Entry point for the PostToolUseFailure hook."""
    tool_name, error_text = _read_tool_result()
    if not tool_name or not error_text:
        return 0

    suggestion = _analyze_tool_result(tool_name, error_text)
    if suggestion:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUseFailure",
                        "additionalContext": suggestion,
                    }
                }
            )
        )

    return 0


def _read_tool_result() -> tuple[str, str]:
    """Read tool name and error from stdin JSON.

    Returns:
        Tuple of (tool_name, error_text). Empty strings when the payload is
        not a non-interrupted PostToolUseFailure event.
    """
    try:
        raw = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        return "", ""

    try:
        data = json.loads(raw)
        if data.get("hook_event_name") != "PostToolUseFailure":
            return "", ""
        is_interrupt = data.get("is_interrupt")
        if is_interrupt is not None and not isinstance(is_interrupt, bool):
            return "", ""
        if is_interrupt is True:
            return "", ""
        tool_name = data.get("tool_name", "")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return "", ""
        error = data.get("error")
        if not isinstance(error, str) or not error.strip():
            return "", ""
    except (json.JSONDecodeError, TypeError, AttributeError):
        return "", ""

    return tool_name, error


def _analyze_tool_result(tool_name: str, error_text: str) -> str:
    """Suggest a memory from a confirmed tool failure.

    PostToolUseFailure is the failure signal. Do not reclassify the event by
    sniffing its display text. Claude documents the top-level ``error`` field
    as variable display text, and valid failures do not always contain words
    such as "error" or "failed".

    Args:
        tool_name: Name of the tool that was called.
        error_text: Error text from the failed tool call.

    Returns:
        Formatted suggestion string, or empty string.
    """
    if not error_text:
        return ""

    pattern = extract_error_pattern(tool_name, error_text)
    return format_suggestion(pattern)


if __name__ == "__main__":
    sys.exit(main())
