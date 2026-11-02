"""Pre-write checks for fix_fences.py: refuse a repair that would harm a file.

Two checks run before ``--write`` replaces a file, and either one refuses it.

``wraps_fence_in_html`` needs no third-party package. A raw HTML block hides
the fences inside it from CommonMark, but fix_fences.py reads them as fences.
CommonMark then sees a balanced file that the scanner "repairs" by appending
a closing fence, so the write edits a well-formed document. The scanner does
not model HTML blocks, so this check finds the shape and the write is refused.
It follows the seven start and end conditions of CommonMark 0.31.2 for blocks
at column zero to three. A block inside a list item or a blockquote is not
seen. It over-refuses on purpose: a refused write costs a manual edit, an
unwanted write edits a good file.

``repair_is_safe`` needs ``markdown-it-py``, which vendored trees do not carry,
so it is skipped when the import fails. It refuses a repair that turns a file
CommonMark reads as balanced into one that leaves a fence open.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

# The scanner's own fence test, passed in by fix_fences.py so the two cannot
# disagree about what a fence is. This module imports nothing from the plugin
# lib, which keeps the ADR-047 bootstrap in one place: the script.
FenceMatcher = Callable[[str], "re.Match[str] | None"]

# Real line terminators only. `str.splitlines` also splits on \x0b, \x0c,
# \x1c-\x1e, U+0085, U+2028 and U+2029, which would shift every line number.
_LINE_SPLIT_RE = re.compile(r"(\r\n|\r|\n)")

_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup"
    "|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame"
    "|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem"
    "|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td"
    "|tfoot|th|thead|title|tr|track|ul"
)
_ATTRIBUTE = r"""\s+[A-Za-z_:][A-Za-z0-9_.:-]*(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?"""

# Start conditions 1 to 7, in the order CommonMark tries them. Conditions 1 to 5
# end at a line holding the matching marker; 6 and 7 end at a blank line.
_HTML_STARTS = (
    re.compile(r"^ {0,3}<(?:script|pre|style|textarea)(?:\s|>|$)", re.IGNORECASE),
    re.compile(r"^ {0,3}<!--"),
    re.compile(r"^ {0,3}<\?"),
    re.compile(r"^ {0,3}<![A-Za-z]"),
    re.compile(r"^ {0,3}<!\[CDATA\["),
    re.compile(rf"^ {{0,3}}</?(?:{_BLOCK_TAGS})(?:\s|/?>|$)", re.IGNORECASE),
    re.compile(
        rf"^ {{0,3}}(?:<[A-Za-z][A-Za-z0-9-]*(?:{_ATTRIBUTE})*\s*/?>|</[A-Za-z][A-Za-z0-9-]*\s*>)\s*$"
    ),
)
_HTML_ENDS = (
    re.compile(r"</(?:script|pre|style|textarea)>", re.IGNORECASE),
    re.compile(r"-->"),
    re.compile(r"\?>"),
    re.compile(r">"),
    re.compile(r"\]\]>"),
)
_ENDS_AT_BLANK_LINE = 5  # index of start condition 6; 6 and 7 have no end marker


def _is_blank(text: str) -> bool:
    """Spaces and tabs only, as CommonMark counts a blank line."""
    return not text.strip(" \t")


def _html_start(line: str) -> int | None:
    """Return the index of the first start condition *line* meets, or None."""
    for index, pattern in enumerate(_HTML_STARTS):
        if pattern.match(line):
            return index
    return None


def _html_ended(index: int, line: str) -> bool:
    """Return True when *line* ends an HTML block started under *index*."""
    if index >= _ENDS_AT_BLANK_LINE:
        return _is_blank(line)
    return _HTML_ENDS[index].search(line) is not None


def _closes_fence(match: re.Match[str], fence: tuple[str, int]) -> bool:
    """Return True when *match* is a bare fence at least as long as the opener."""
    marker = match.group("fence")
    return marker[0] == fence[0] and len(marker) >= fence[1] and _is_blank(match.group("info"))


def wraps_fence_in_html(text: str, fence_match: FenceMatcher) -> bool:
    """Return True when a fence-looking line sits inside a raw HTML block.

    Fenced code is skipped, so HTML shown as an example inside a fence does not
    count. A start line is checked against its own end marker, so ``<pre>x</pre>``
    closes on the line that opens it. *fence_match* is the scanner's fence test.
    """
    fence: tuple[str, int] | None = None
    html: int | None = None
    for line in _LINE_SPLIT_RE.sub("\n", text).split("\n"):
        match = fence_match(line)
        if html is not None:
            if match is not None:
                return True
            if _html_ended(html, line):
                html = None
            continue
        if fence is not None:
            if match is not None and _closes_fence(match, fence):
                fence = None
            continue
        if match is not None:
            fence = (match.group("fence")[0], len(match.group("fence")))
            continue
        html = _html_start(line)
        if html is not None and html < _ENDS_AT_BLANK_LINE and _html_ended(html, line):
            html = None
    return False


def _load_reference() -> Any:
    """Return the CommonMark reference parser, or None when it is not installed.

    Vendored trees carry no third-party packages, so the import is optional.
    """
    try:
        from markdown_it import MarkdownIt
    except ImportError:
        return None
    return MarkdownIt("commonmark")


def _reference_lines(text: str) -> list[str]:
    """Split *text* the way the reference parser numbers lines.

    Not ``str.splitlines``: its extra separators shift every later ``token.map``.
    """
    lines = _LINE_SPLIT_RE.sub("\n", text).split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # text ended with a terminator; no empty final line
    return lines


def leaves_fence_open(reference: Any, text: str) -> bool:
    """Return True when a fence in *text* reaches EOF with no closing marker.

    Read from the token. A span longer than opener plus body was closed by a
    marker; "no marker" alone is not "open", since a fence also ends with its
    list item, so the token must also reach the last line.
    """
    source = _reference_lines(text)
    for token in reference.parse(text):
        if token.type != "fence" or not token.map:
            continue
        span = token.map[1] - token.map[0]
        body = len(_reference_lines(token.content))
        marked = span - 1 - body >= 1
        if not marked and token.map[1] >= len(source):
            return True
    return False


def repair_is_safe(reference: Any, before: str, after: str) -> bool:
    """Return False when the repair would turn a balanced file unclosed.

    With no reference parser there is nothing to judge against: allowed.
    """
    if reference is None:
        return True
    return leaves_fence_open(reference, before) or not leaves_fence_open(reference, after)


def refusal_reason(
    reference: Any, before: str, after: str, fence_match: FenceMatcher
) -> str | None:
    """Return why a repair of *before* into *after* must not be written, or None."""
    if wraps_fence_in_html(before, fence_match):
        return "a fence sits inside a raw HTML block, which the scanner does not model"
    if not repair_is_safe(reference, before, after):
        return "the repair would turn a balanced file into an unclosed one"
    return None
