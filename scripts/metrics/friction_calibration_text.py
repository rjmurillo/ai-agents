"""Text helpers shared by the calibration scan and excerpt (REQ-048 TASK-001)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SNIPPET_CHARS = 2000  # raw text kept per candidate until the parent redacts it


def first_error_line(text: str) -> str:
    """The first non-blank line, capped at ``SNIPPET_CHARS``."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:SNIPPET_CHARS]
    return ""


# Context kept before a matched term, so a later 200-character clip keeps it.
MATCH_LEAD_CHARS = 80


def matching_line(text: str, term: str) -> str:
    """The first line holding ``term`` (any case), so a judge sees what matched.

    A long line is windowed to start shortly before the term.
    """
    needle = term.lower()
    line = next((line.strip() for line in text.splitlines() if needle in line.lower()), "")
    start = max(0, line.lower().find(needle) - MATCH_LEAD_CHARS)
    return line[start : start + SNIPPET_CHARS]


# Injected harness text in user or assistant text blocks, not agent prose.
_INJECTED_PREFIXES = ("<system-reminder>", "<local-command", "<command-", "<total_tokens>")
_HOOK_OUTPUT = re.compile(r"^[A-Za-z]+(?::[A-Za-z|*]+)? hook (?:success|additional context|error)")


def is_injected(text: str) -> bool:
    """True for harness-injected text (reminders, command echoes, hook output)."""
    stripped = text.lstrip()
    return stripped.startswith(_INJECTED_PREFIXES) or bool(_HOOK_OUTPUT.match(stripped))


def user_text(record: Mapping[str, Any]) -> str:
    """Full text of a user record: a string, or its text blocks joined."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [
        b["text"]
        for b in content
        if isinstance(b, Mapping) and b.get("type") == "text" and isinstance(b.get("text"), str)
    ]
    return " ".join(parts)
