# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream file: src/lib/reason-extract.ts (stripTrailers, stripImporterMetadata,
# hasImporterMetadata, and the patterns they use). The sentence scoring lives in adr_reason.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Commit text cleaning for reason extraction: importer metadata and trailers.

A stored commit loses its trailers by shape, not by list: the run of ``Key: value``
lines that ends its last paragraph. Standard library only, no I/O.

Regex notes. Module-level patterns compile with ``re.ASCII`` so ``\\b``, ``\\w``, ``\\d`` and
case folding match the JavaScript source. ``$`` without a multiline flag is ``\\Z``
here, because Python's ``$`` also matches before a trailing newline. ASCII ``\\s`` does not match Unicode spaces such as U+00A0, which JavaScript's ``\\s`` does. ``flat`` stays
Unicode-aware, as ``\\s`` is in JavaScript.
"""

from __future__ import annotations

import re

__all__ = [
    "CONVENTIONAL_PREFIX",
    "FIXES_ONLY",
    "TRAILER",
    "flat",
    "has_importer_metadata",
    "strip_importer_metadata",
    "strip_trailers",
]

_A = re.ASCII
_I = re.IGNORECASE | re.ASCII

# The importer appends: Author, Date, optional Files changed list, optional URL.
_IMPORTER_METADATA = re.compile(
    r"\n\nAuthor: [^\n]*\n\nDate: [^\n]*(?:\n\n(?:Files changed:|URL:)[\s\S]*)?\Z", _A
)
_NEWLINES = re.compile(r"\r\n?")

TRAILER = re.compile(
    r"^\s*(?:co-authored-by|signed-off-by|reviewed-by|reviewed-on|acked-by|tested-by"
    r"|reported-by|suggested-by|helped-by|change-id|pr-url|cc|bug|jira|issue)\s*:",
    _I,
)
_ISSUE_REF = r"(?:#\d+|gh-\d+|[\w.-]+/[\w.-]+#\d+|https?://\S+)"
FIXES_ONLY = re.compile(
    r"^\s*(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?|refs?|see|related to|part of)\b:?\s*"
    + _ISSUE_REF
    + r"(?:[\s,;&]+(?:and\s+)?"
    + _ISSUE_REF
    + r")*\s*[.]?\s*\Z",
    _I,
)

# Lowercase types only and a required space: the source does not use an i flag here.
CONVENTIONAL_PREFIX = re.compile(r"^[a-z]+(?:\([^)]*\))?!?:\s+", _A)

# A line shaped like a git trailer: one key token, a colon, a space, a value. A line
# indented by four spaces or a tab is a code example, not a trailer.
_TRAILER_SHAPE = re.compile(r"^ {0,3}([A-Za-z][A-Za-z0-9-]*):[ \t]+(\S.*)\Z", _A)
# Keys that introduce prose, never provenance.
_PROSE_KEY = re.compile(r"^(?:why|reason|rationale|motivation|note)\Z", _I)
# "Issue: users get a 500 when the token expires" states the problem and "Issue: #123"
# points at one. Only the pointer is a trailer.
_REFERENCE_KEY = re.compile(r"^(?:issue|bug)\Z", _I)
_REFERENCE = r"(?:" + _ISSUE_REF + r"|[A-Z][A-Z0-9]+-\d+|\d+)"
_REFERENCES_ONLY = re.compile(
    r"^" + _REFERENCE + r"(?:[\s,;&]+(?:and\s+)?" + _REFERENCE + r")*\s*[.]?\s*\Z", _A
)
# A longer value is a sentence, not a list of references. It also bounds the match above.
_MAX_REFERENCE_VALUE_CHARS = 200


def flat(text: str) -> str:
    """Collapse every whitespace run to one space and trim."""
    return re.sub(r"\s+", " ", text).strip()


def strip_importer_metadata(text: str) -> str:
    """The Author/Date/Files changed/URL block the git importer appends, removed."""
    return _IMPORTER_METADATA.sub("", _NEWLINES.sub("\n", text), count=1)


def has_importer_metadata(text: str) -> bool:
    """True for a stored git commit: only the git importer appends the Author/Date block."""
    return _IMPORTER_METADATA.search(_NEWLINES.sub("\n", text)) is not None


def _is_trailer_line(line: str) -> bool:
    match = _TRAILER_SHAPE.match(line)
    if not match:
        return False
    key = match.group(1)
    value = match.group(2).strip()
    # "fix: retry on 503": conventional-commit form is a sub-commit subject in a squash body.
    if _PROSE_KEY.search(key) or CONVENTIONAL_PREFIX.search(line.strip()):
        return False
    if _REFERENCE_KEY.search(key):
        return len(value) <= _MAX_REFERENCE_VALUE_CHARS and bool(_REFERENCES_ONLY.search(value))
    return True


def strip_trailers(text: str, subject: str | None = None) -> str:
    """A commit message without its trailers.

    Removes the run of ``Key: value`` lines that ends the last paragraph, with the
    blank lines above it. A ``Key: value`` line in an earlier paragraph, or with a
    prose line under it, stays. Never a trailer: a prose label (Why, Reason,
    Rationale, Motivation, Note), ``Issue:`` or ``Bug:`` followed by prose, and a
    line in conventional-commit form. ``subject``, when given, is the commit's own
    first line, which is never a trailer whatever its shape. Text with no trailer is
    returned unchanged.
    """
    lines = text.split("\n")
    end = len(lines)
    while end > 0 and not lines[end - 1].strip():
        end -= 1
    start = end
    while start > 0 and _is_trailer_line(lines[start - 1]):
        start -= 1
    if start == 0 and end > 0 and subject is not None and flat(lines[0]) == flat(subject):
        start = 1
    if start == end:
        return text
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    return "\n".join(lines[:start])
