"""Placement-marker parsing for check_memory_placement.py (#5391, #6506).

A memory opts out of the normative-policy check with a standalone line
``<!-- placement: evidence; reason: ... -->``. The reason must hold at least
``MIN_SUPPRESSION_REASON_CHARS`` characters after trimming, so a one-word
reason such as "ok" cannot silence the check. A marker that is present but
malformed or too short is invalid and does not downgrade the file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.utils.markdown_parser import blank_non_prose_block_lines  # noqa: E402

MIN_SUPPRESSION_REASON_CHARS = 20

# The marker must stand alone on its line (not inside an inline code span or
# another HTML element) and the reason must start with a non-whitespace char.
_VALID_SUPPRESSION_RE = re.compile(
    r"^[ \t]*<!--\s*placement:\s*evidence;\s*reason:\s*(\S[^>]*?)\s*-->[ \t]*$", re.MULTILINE
)
# Looser sibling: detects a marker that is present but malformed.
_ANY_SUPPRESSION_RE = re.compile(r"<!--\s*placement:\s*evidence;\s*reason:\s*(.*?)-->", re.DOTALL)

_VALID_PLACEHOLDER = "__valid_placement_marker__"
_INVALID_PLACEHOLDER = "__invalid_placement_marker__"


def _mark_standalone_suppression(match: re.Match[str]) -> str:
    """Swap a standalone marker for the valid placeholder, or the invalid one if too short."""
    if len(match.group(1).strip()) >= MIN_SUPPRESSION_REASON_CHARS:
        return _VALID_PLACEHOLDER
    return _INVALID_PLACEHOLDER


def suppression_status(text: str) -> tuple[bool, bool]:
    """Return (suppressed, invalid_suppression) for a placement marker in ``text``."""
    marked = _VALID_SUPPRESSION_RE.sub(_mark_standalone_suppression, text)
    marked = _ANY_SUPPRESSION_RE.sub(_INVALID_PLACEHOLDER, marked)
    prose = blank_non_prose_block_lines(marked)
    if _VALID_PLACEHOLDER in prose:
        return True, False
    if _INVALID_PLACEHOLDER in prose:
        return False, True
    return False, False
