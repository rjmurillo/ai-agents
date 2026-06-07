#!/usr/bin/env python3
"""YAML frontmatter parsing for validation scripts.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223) so the pre-PR
runner stays smaller and the frontmatter parser has a single home that other
validators can reuse. The parser reads the leading ``---`` fenced block with
the same YAML loader that downstream agent hosts use, so colon-bearing plain
scalars fail locally instead of becoming silent runtime load failures.
"""

from __future__ import annotations

from typing import Any

import yaml


def _parse_yaml_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter from markdown text.

    Returns parsed dict or None if no frontmatter found.
    Returns None when the YAML block is malformed or not a mapping.
    """
    if not text.startswith("---"):
        return None

    end_index = text.find("\n---", 3)
    if end_index == -1:
        return None

    frontmatter_text = text[4:end_index].strip()
    try:
        result = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None
    return result if isinstance(result, dict) else None
