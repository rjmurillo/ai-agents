"""Failure pattern extraction from tool results.

Extracts a learnable pattern from a tool failure and formats it as a
memory suggestion. Used by the PostToolUseFailure hook.
"""

from __future__ import annotations

import re

_ERROR_INDICATORS = (
    "error", "exception", "traceback", "failed", "failure",
    "permission denied", "not found", "timeout",
)

# An indicator glued to an identifier separator is part of a name, not a
# report. A bare substring test read "failure" inside `analyze_pr_failure.py`,
# so a plain `ls scripts` looked like a tool failure and injected a memory
# suggestion into the model context (issue #4011). Only `_` and `-` are
# excluded on each side: a letter boundary must stay open for "ValueError" and
# a trailing letter must stay open for "3 errors".
_ERROR_PATTERN = re.compile(
    r"(?<![-_])(?:"
    + "|".join(re.escape(word) for word in _ERROR_INDICATORS)
    + r")(?![-_])",
    re.IGNORECASE,
)

# Patterns that look like errors but indicate success (e.g. "0 errors", "no errors").
_FALSE_POSITIVE_PATTERN = re.compile(
    r"\b(?:0|no|zero|without)\s+(?:error|exception|failure)s?\b", re.IGNORECASE
)

_MAX_PATTERN_LENGTH = 200
_MAX_SUGGESTION_LENGTH = 300


def extract_error_pattern(tool_name: str, error_text: str) -> dict[str, str]:
    """Extract a learnable pattern from a tool failure.

    Scans the error text for the first line containing an error indicator.
    Returns a dict with tool_name, pattern, and a suggested memory.

    Args:
        tool_name: Name of the tool that failed.
        error_text: Error output from the tool.

    Returns:
        Dict with keys: tool_name, pattern, suggested_memory.
    """
    pattern = _find_error_line(error_text)
    suggested = f"Tool '{tool_name}' failed with: {pattern}"
    suggested = suggested[:_MAX_SUGGESTION_LENGTH]

    return {
        "tool_name": tool_name,
        "pattern": pattern,
        "suggested_memory": suggested,
    }


def format_suggestion(pattern: dict[str, str]) -> str:
    """Format a memory suggestion for stderr output.

    Formats an error pattern dict as a tagged suggestion block.

    Args:
        pattern: Dict from extract_error_pattern.

    Returns:
        Formatted suggestion string for stderr.
    """
    tool_name = pattern.get("tool_name", "unknown")
    suggestion_type = pattern.get("type", "learning")
    content = pattern.get("pattern") or pattern.get("content", "")
    suggested = pattern.get("suggested_memory", "")

    if not suggested:
        suggested = f"Notable output from {tool_name}: {content}"
        suggested = suggested[:_MAX_SUGGESTION_LENGTH]

    trigger = f"{tool_name} failure" if suggestion_type == "learning" else f"{tool_name} output"

    lines = [
        "<memory-suggestion>",
        f"type: {suggestion_type}",
        f"trigger: {trigger}",
    ]

    if pattern.get("pattern"):
        lines.append(f"pattern: {content}")

    lines.extend([
        "suggested_memory: |",
        f"  {suggested}",
        f"citation: tool_result:{tool_name}",
        "</memory-suggestion>",
    ])
    return "\n".join(lines)


def has_error_indicators(result_text: str) -> bool:
    """Check if the result contains genuine error indicators.

    Filters out false positives like '0 errors' or 'no errors' that
    indicate success rather than failure.
    """
    if not _ERROR_PATTERN.search(result_text):
        return False
    # Strip false-positive phrases before re-checking.
    cleaned = _FALSE_POSITIVE_PATTERN.sub("", result_text)
    return bool(_ERROR_PATTERN.search(cleaned))


def _find_error_line(result_text: str) -> str:
    """Extract the first error-like line from the result."""
    for line in result_text.splitlines():
        if _ERROR_PATTERN.search(line):
            return line.strip()[:_MAX_PATTERN_LENGTH]
    return " ".join(result_text.split())[:_MAX_PATTERN_LENGTH]
