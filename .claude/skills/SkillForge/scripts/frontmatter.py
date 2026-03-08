"""Shared frontmatter parsing utilities for skill validation.

Provides common YAML frontmatter parsing logic used by SkillForge
validation scripts (skill_modularity_audit.py) and the project-level
skill_size.py validator.
"""

from __future__ import annotations

import re


def has_size_exception(content: str) -> bool:
    """Check if YAML frontmatter declares a size exception.

    Parses the frontmatter block delimited by ``---`` and looks for
    ``size-exception: true``.

    Args:
        content: Full file content (must start with ``---`` for frontmatter).

    Returns:
        True if frontmatter contains ``size-exception: true``, False otherwise.
    """
    if not content.startswith("---"):
        return False

    lines = content.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            frontmatter = "\n".join(lines[1:i])
            return bool(
                re.search(r"^size-exception:\s*true", frontmatter, re.MULTILINE)
            )
    return False
