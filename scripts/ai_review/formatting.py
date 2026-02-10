"""Markdown and display formatting for AI review outputs."""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Verdict alert types
# ---------------------------------------------------------------------------

_ALERT_TYPE_MAP: dict[str, str] = {
    "PASS": "TIP",
    "COMPLIANT": "TIP",
    "WARN": "WARNING",
    "PARTIAL": "WARNING",
    "CRITICAL_FAIL": "CAUTION",
    "REJECTED": "CAUTION",
    "FAIL": "CAUTION",
}

_FAIL_EXIT_VERDICTS = frozenset({"CRITICAL_FAIL", "REJECTED", "FAIL"})

_EMOJI_MAP: dict[str, str] = {
    "PASS": "\u2705",
    "COMPLIANT": "\u2705",
    "WARN": "\u26a0\ufe0f",
    "PARTIAL": "\u26a0\ufe0f",
    "CRITICAL_FAIL": "\u274c",
    "REJECTED": "\u274c",
    "FAIL": "\u274c",
}


def get_verdict_alert_type(verdict: str) -> str:
    """Map verdict to GitHub alert type: TIP, WARNING, CAUTION, or NOTE."""
    return _ALERT_TYPE_MAP.get(verdict, "NOTE")


def get_verdict_exit_code(verdict: str) -> int:
    """Return 1 for failure verdicts, 0 otherwise."""
    return 1 if verdict in _FAIL_EXIT_VERDICTS else 0


def get_verdict_emoji(verdict: str) -> str:
    """Map verdict to display emoji."""
    return _EMOJI_MAP.get(verdict, "\u2754")


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


def format_collapsible_section(title: str, content: str) -> str:
    """Create an HTML details/summary section for GitHub markdown."""
    return f"<details>\n<summary>{title}</summary>\n\n{content}\n\n</details>"


def format_verdict_alert(verdict: str, message: str = "") -> str:
    """Format a verdict using GitHub's markdown alert syntax."""
    alert_type = get_verdict_alert_type(verdict)
    if message:
        return (
            f"> [!{alert_type}]\n"
            f"> **Verdict: {verdict}**\n"
            f">\n"
            f"> {message}"
        )
    return f"> [!{alert_type}]\n> **Verdict: {verdict}**"


def format_markdown_table_row(columns: list[str]) -> str:
    """Create a pipe-delimited markdown table row."""
    return "| " + " | ".join(columns) + " |"


def convert_to_json_escaped(input_string: str) -> str:
    """Escape a string for JSON embedding."""
    if not input_string:
        return '""'
    return json.dumps(input_string)
