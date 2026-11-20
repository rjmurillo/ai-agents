"""Shared frontmatter parsing utilities for skill validation.

Provides common YAML frontmatter parsing logic used by SkillForge
validation scripts (skill_modularity_audit.py) and the project-level
skill_size.py validator. The fence rule is the one shared parser,
``hook_utilities.frontmatter_block``.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ADR-047 keeps this bootstrap inline because imports need sys.path first.
_PLUGIN_ROOT = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _PLUGIN_ROOT:
    _LIB_DIR = Path(_PLUGIN_ROOT) / "lib"
else:
    _LIB_DIR = Path(__file__).resolve().parents[3] / "lib"

if not os.path.isdir(_LIB_DIR):
    raise RuntimeError(
        "Expected portability helper lib directory not found: "
        f"{_LIB_DIR}. Set COPILOT_PLUGIN_ROOT or CLAUDE_PLUGIN_ROOT to the "
        "plugin root, or run from an ai-agents checkout."
    )
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from hook_utilities.frontmatter_block import split_frontmatter  # noqa: E402

_SIZE_EXCEPTION = re.compile(r"(?im)^\s*size-exception:\s*true\s*(?:#.*)?$")


def has_size_exception(content: str) -> bool:
    """Check if YAML frontmatter declares a size exception.

    Reads the leading frontmatter block with
    ``hook_utilities.frontmatter_block.split_frontmatter`` and looks for
    ``size-exception: true`` in its text. No YAML is loaded.

    Args:
        content: Full file content.

    Returns:
        True if frontmatter contains ``size-exception: true``, False otherwise.
    """
    split = split_frontmatter(content)
    if not split.found:
        return False
    return bool(_SIZE_EXCEPTION.search(split.raw))
