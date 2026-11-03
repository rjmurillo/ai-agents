"""Text helpers shared by the calibration scan and excerpt (REQ-048 TASK-001)."""

from __future__ import annotations

SNIPPET_CHARS = 2000  # raw text kept per candidate until the parent redacts it


def first_error_line(text: str) -> str:
    """The first non-blank line, capped at ``SNIPPET_CHARS``."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:SNIPPET_CHARS]
    return ""


def matching_line(text: str, term: str) -> str:
    """The first line holding ``term`` (any case), so a judge sees what matched."""
    needle = term.lower()
    line = next((line.strip() for line in text.splitlines() if needle in line.lower()), "")
    return line[:SNIPPET_CHARS]
