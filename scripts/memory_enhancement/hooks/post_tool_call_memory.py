#!/usr/bin/env python3
"""Hook: post_tool_call - Capture facts from tool results.

Analyzes tool output for novel information worth remembering.
Captures patterns from failures for future avoidance.
Governed mode: suggests via stderr, never auto-creates memories.
"""

from __future__ import annotations

import json
import sys

_ERROR_INDICATORS = frozenset({
    "error", "exception", "traceback", "failed", "failure",
    "permission denied", "not found", "timeout",
})

_MAX_PATTERN_LENGTH = 200
_MAX_SUGGESTION_LENGTH = 300


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
    if _is_error_result(result_text):
        return _format_error_suggestion(tool_name, result_text)

    if _has_notable_content(result_text):
        return _format_content_suggestion(tool_name, result_text)

    return ""


def _is_error_result(result_text: str) -> bool:
    """Check if the result contains error indicators."""
    lower = result_text.lower()
    return any(indicator in lower for indicator in _ERROR_INDICATORS)


def _has_notable_content(result_text: str) -> bool:
    """Check if the result contains file paths or code references worth noting."""
    indicators = (".py", ".ts", ".js", ".md", "def ", "class ", "function ")
    lower = result_text.lower()
    return any(ind in lower for ind in indicators)


def _extract_error_pattern(result_text: str) -> str:
    """Extract the first error-like line from the result."""
    for line in result_text.splitlines():
        lower = line.lower().strip()
        if any(ind in lower for ind in _ERROR_INDICATORS):
            return line.strip()[:_MAX_PATTERN_LENGTH]
    return result_text[:_MAX_PATTERN_LENGTH]


def _format_error_suggestion(tool_name: str, result_text: str) -> str:
    """Format a memory suggestion for a tool failure.

    Args:
        tool_name: Name of the tool that failed.
        result_text: Error output from the tool.

    Returns:
        Formatted YAML-like suggestion block for stderr.
    """
    pattern = _extract_error_pattern(result_text)
    suggested = f"Tool '{tool_name}' failed with: {pattern}"
    suggested = suggested[:_MAX_SUGGESTION_LENGTH]

    lines = [
        "<memory-suggestion>",
        "type: learning",
        f"trigger: {tool_name} failure",
        f"pattern: {pattern}",
        "suggested_memory: |",
        f"  {suggested}",
        f"citation: tool_result:{tool_name}",
        "</memory-suggestion>",
    ]
    return "\n".join(lines)


def _format_content_suggestion(tool_name: str, result_text: str) -> str:
    """Format a memory suggestion for notable tool output.

    Args:
        tool_name: Name of the tool that produced output.
        result_text: Output containing notable content.

    Returns:
        Formatted YAML-like suggestion block for stderr.
    """
    snippet = result_text[:_MAX_SUGGESTION_LENGTH]

    lines = [
        "<memory-suggestion>",
        "type: observation",
        f"trigger: {tool_name} output",
        "suggested_memory: |",
        f"  Notable output from {tool_name}: {snippet}",
        f"citation: tool_result:{tool_name}",
        "</memory-suggestion>",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
