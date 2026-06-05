#!/usr/bin/env python3
"""Minimal YAML frontmatter parsing for validation scripts.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223) so the pre-PR
runner stays smaller and the frontmatter parser has a single home that other
validators can reuse. The parser is intentionally minimal (no PyYAML
dependency): it reads a leading ``---`` fenced block of flat ``key: value``
pairs, strips inline comments and quotes, and coerces booleans and integers.
"""

from __future__ import annotations

from typing import Any


def _parse_yaml_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter from markdown text.

    Returns parsed dict or None if no frontmatter found.
    Uses a minimal parser to avoid external dependencies.
    """
    if not text.startswith("---"):
        return None

    end_index = text.find("\n---", 3)
    if end_index == -1:
        return None

    frontmatter_text = text[4:end_index].strip()
    result: dict[str, Any] = {}

    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        colon_pos = line.find(":")
        if colon_pos == -1:
            continue

        key = line[:colon_pos].strip()
        value = line[colon_pos + 1 :].strip()

        # Strip inline YAML comments (e.g., "APPROVED  # valid values")
        # Only strip if not inside quotes
        if value and value[0] not in ('"', "'"):
            comment_pos = value.find("#")
            if comment_pos > 0:
                value = value[:comment_pos].strip()

        # Strip quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        # Parse booleans
        if value.lower() == "true":
            result[key] = True
        elif value.lower() == "false":
            result[key] = False
        # Parse integers
        elif value.isdigit():
            result[key] = int(value)
        else:
            result[key] = value

    return result
