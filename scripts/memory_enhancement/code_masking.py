"""Blank out markdown code so citation parsing ignores documented examples.

A memory that documents the ``[cite:type](target)`` syntax writes an example
inside a fenced block or a code span. That example describes the syntax; it is
not a claim about the repository. ``mask_code`` replaces every code character
with a space and keeps newlines, so offsets and line structure survive and
the citation pattern can no longer match inside code.

Handled: backtick and tilde fences at any indent (so list-item fences count), unterminated
fences that run to the end of the text, and inline code spans. A backtick fence
inside a blockquote has no line-anchored opener, but its backtick runs pair as
one multi-line code span, so it is blanked as well. A tilde fence there is not.
"""

from __future__ import annotations

import re

# Opener: three or more backticks or tildes, at line start after optional
# indent. A backtick fence's info string may not hold a backtick (CommonMark
# 0.31.2 section 4.5), so such a line is ordinary text.
_FENCE_OPEN = re.compile(
    r"^[ \t]*(?:(`{3,})(?![^\n]*`)|(~{3,}))[^\n]*(?:\n|\Z)",
    re.MULTILINE,
)

# A code span opens on a backtick run and closes on a run of the same length.
# The lookarounds keep both runs maximal. A span never crosses a blank line.
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(?:[^\n]|\n(?!\s*\n))+?(?<!`)\1(?!`)")


def _blank(text: str, start: int, end: int) -> str:
    """Return ``text`` with ``[start, end)`` replaced by spaces, newlines kept."""
    return text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]


def _fence_ranges(text: str) -> list[tuple[int, int]]:
    """Return (start, end) for each fenced block; an unclosed fence runs to the end.

    The closer must use the opener's character and be at least as long, with
    nothing after it but whitespace.
    """
    ranges: list[tuple[int, int]] = []
    pos = 0
    while (opener := _FENCE_OPEN.search(text, pos)) is not None:
        run = opener.group(1) or opener.group(2)
        closer = re.compile(
            rf"^[ \t]*{re.escape(run[0])}{{{len(run)},}}[ \t]*$",
            re.MULTILINE,
        ).search(text, opener.end())
        end = closer.end() if closer else len(text)
        ranges.append((opener.start(), end))
        pos = max(end, opener.end())
    return ranges


def mask_code(text: str) -> str:
    """Return ``text`` with fenced blocks and inline code spans blanked."""
    for start, end in _fence_ranges(text):
        text = _blank(text, start, end)
    return _CODE_SPAN.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), text)
