#!/usr/bin/env python3
"""Hook: post_tool_call - Capture facts from tool results.

Analyzes tool output for novel information worth remembering.
Captures patterns from failures for future avoidance.
Governed mode: suggests via stderr, never auto-creates memories.
"""

from __future__ import annotations

import json
import sys

from ..extraction import (
    extract_error_pattern,
    extract_facts,
    format_suggestion,
    has_error_indicators,
    has_notable_content,
)


def main() -> int:
    """Entry point for the post_tool_call hook."""
    tool_name, result_text = _read_tool_result()
    if not tool_name:
        return 0

    suggestion = _analyze_tool_result(tool_name, result_text)
    if suggestion:
        print(suggestion, file=sys.stderr)

    return 0


def _read_tool_result() -> tuple[str, str]:
    """Read tool name and result from stdin JSON.

    Returns:
        Tuple of (tool_name, result_text). Empty strings on parse failure.
    """
    try:
        raw = sys.stdin.read()
    except (OSError, UnicodeDecodeError):
        return "", ""

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return "", ""

    tool_name = str(data.get("tool_name", ""))
    result = str(data.get("result", ""))
    return tool_name, result


def _analyze_tool_result(tool_name: str, result_text: str) -> str:
    """Analyze tool result and generate memory suggestion if warranted.

    Args:
        tool_name: Name of the tool that was called.
        result_text: Output from the tool call.

    Returns:
        Formatted suggestion string, or empty string.
    """
    if has_error_indicators(result_text):
        pattern = extract_error_pattern(tool_name, result_text)
        return format_suggestion(pattern)

    if has_notable_content(result_text):
        facts = extract_facts(tool_name, result_text)
        if facts:
            return format_suggestion(facts[0])

    return ""


if __name__ == "__main__":
    sys.exit(main())
