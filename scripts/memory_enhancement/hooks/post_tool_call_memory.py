#!/usr/bin/env python3
"""Hook: post_tool_call - Capture learnable failures from tool results.

Analyzes tool output for an error worth remembering and suggests a memory
for it. Governed mode: suggests via stderr, never auto-creates memories.
"""

from __future__ import annotations

import json
import sys

from ..extraction import (
    extract_error_pattern,
    format_suggestion,
    has_error_indicators,
)


def main() -> int:
    """Entry point for the post_tool_call hook."""
    tool_name, result_text = _read_tool_result()
    if not tool_name:
        return 0

    suggestion = _analyze_tool_result(tool_name, result_text)
    if suggestion:
        print(suggestion, file=sys.stderr)
        return 2

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
        tool_name = str(data.get("tool_name", ""))
        result = str(data.get("result") or "")
        if not result:
            result = _flatten_tool_response(data.get("tool_response"))
    except (json.JSONDecodeError, TypeError, AttributeError):
        return "", ""

    return tool_name, result


# Claude Code's PostToolUse payload carries the output under "tool_response",
# not "result", so a hook that reads only "result" is inert against the real
# harness (issue #4011). "result" stays first for the payload shapes that do
# send it.
_TOOL_RESPONSE_KEYS = ("stdout", "stderr", "content", "output")


def _flatten_tool_response(response: object) -> str:
    """Reduce a tool_response of any shape to searchable text."""
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        parts = [str(response[key]) for key in _TOOL_RESPONSE_KEYS if response.get(key)]
        return "\n".join(parts)
    if isinstance(response, list):
        return "\n".join(_flatten_tool_response(item) for item in response)
    return str(response)


def _analyze_tool_result(tool_name: str, result_text: str) -> str:
    """Suggest a memory when the tool failed in a learnable way.

    Failure is the only signal worth an interrupt. The hook is registered
    without a matcher, so it observes every tool call; a success path that
    fired on any output mentioning a file extension turned roughly 40% of
    ordinary calls into a content-free suggestion in the model context
    ("Notable output from Bash: search.py" for a bare `ls`). Errors are
    tool-agnostic, which is why the registration stays matcher-free.

    Args:
        tool_name: Name of the tool that was called.
        result_text: Output from the tool call.

    Returns:
        Formatted suggestion string, or empty string.
    """
    if has_error_indicators(result_text):
        pattern = extract_error_pattern(tool_name, result_text)
        return format_suggestion(pattern)

    return ""


if __name__ == "__main__":
    sys.exit(main())
