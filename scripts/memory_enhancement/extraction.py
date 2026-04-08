"""Fact and pattern extraction from tool results.

Extracts learnable patterns from tool failures and facts from
successful tool output. Used by the post_tool_call hook.
"""

from __future__ import annotations

import re

_ERROR_INDICATORS = frozenset({
    "error", "exception", "traceback", "failed", "failure",
    "permission denied", "not found", "timeout",
})

# Patterns that look like errors but indicate success (e.g. "0 errors", "no errors").
_FALSE_POSITIVE_PATTERN = re.compile(
    r"\b(?:0|no|zero|without)\s+(?:error|exception|failure)s?\b", re.IGNORECASE
)

_CONTENT_INDICATORS = (".py", ".ts", ".js", ".md", "def ", "class ", "function ")

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


def extract_facts(tool_name: str, result_text: str) -> list[dict[str, str]]:
    """Extract facts from successful tool output.

    Identifies lines containing file paths or code references.
    Each fact is a dict with tool_name, content, and type.

    Args:
        tool_name: Name of the tool that produced output.
        result_text: Output from the tool call.

    Returns:
        List of dicts with keys: tool_name, content, type.
    """
    facts: list[dict[str, str]] = []
    for line in result_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(ind in lower for ind in _CONTENT_INDICATORS):
            facts.append({
                "tool_name": tool_name,
                "content": stripped[:_MAX_SUGGESTION_LENGTH],
                "type": "observation",
            })
    return facts


def format_suggestion(pattern: dict[str, str]) -> str:
    """Format a memory suggestion for stderr output.

    Accepts either an error pattern dict or a fact dict and
    formats it as a tagged suggestion block.

    Args:
        pattern: Dict from extract_error_pattern or extract_facts.

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
    lower = result_text.lower()
    if not any(indicator in lower for indicator in _ERROR_INDICATORS):
        return False
    # Strip false-positive phrases before re-checking.
    cleaned = _FALSE_POSITIVE_PATTERN.sub("", lower)
    return any(indicator in cleaned for indicator in _ERROR_INDICATORS)


def has_notable_content(result_text: str) -> bool:
    """Check if the result contains file paths or code references."""
    lower = result_text.lower()
    return any(ind in lower for ind in _CONTENT_INDICATORS)


def _find_error_line(result_text: str) -> str:
    """Extract the first error-like line from the result."""
    for line in result_text.splitlines():
        lower = line.lower().strip()
        if any(ind in lower for ind in _ERROR_INDICATORS):
            return line.strip()[:_MAX_PATTERN_LENGTH]
    return result_text[:_MAX_PATTERN_LENGTH]
