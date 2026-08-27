#!/usr/bin/env python3
"""Anchor semantics for the citation-freshness gate (issue #5337).

Extracted from ``check_citation_freshness.py`` at the file-size ceiling,
alongside its sibling ``citation_head_state.py``: this module owns what
counts as a citation, what counts as an anchor the citing text names, and
which slice of a line each citation on it owns. The gate module keeps the
policy (exemptions, the ignore marker, findings, wiring).

Anchors carry a deliberate noise floor: backtick spans need 3 or more
characters, double-quoted phrases 4 or more, and bare identifiers 5 or
more. One- and two-letter tokens (``x``, ``OK``, ``a_b``) appear in
nearly every line of code, so treating them as assertions would fail
correct citations wholesale; a citation whose only nearby tokens are
that short is checked for existence and range, not content.
"""

from __future__ import annotations

import re

# Text formats this repository actually cites; extend when a real
# citation to a new format appears rather than enumerating every
# extension in existence (each entry adds matcher surface).
_EXTENSIONS = (
    "py|md|yml|yaml|json|jsonc|xml|csv|ps1|psm1|psd1|sh|ts|js|toml|txt|ini|cfg|html|css|ipynb"
)

# A citation: a repo path with a known extension, then :N or :N-M. The
# path class excludes backticks, quotes, parens, and colons, so
# surrounding markup never leaks into the path. The left boundary
# rejects a start preceded by a path character in either separator
# style, so an absolute filesystem path (/home/... or C:\tmp\...) never
# yields a phantom repo citation from its tail, and the lookahead keeps
# parent-relative ../ paths out; ./ is still accepted (the gate strips
# that prefix). The slash group is optional so tracked root files
# (.markdownlint-cli2.yaml:138) are in scope; the gate skips a
# slashless name not tracked at the repo root, which is what keeps
# illustrative snippets (auth.ts:47) out.
_CITATION = re.compile(
    rf"(?<![\w./\\-])(?!\.\.[/\\])"
    rf"(?P<path>[\w.-]+(?:/[\w.-]+)*\.(?:{_EXTENSIONS})):(?P<start>\d+)(?:-(?P<end>\d+))?\b"
)

_URL = re.compile(r"https?://\S+")
_BACKTICK_SPAN = re.compile(r"`+([^`]+)`+")
# Double-quoted phrases are anchors too: prose quotes the cited contract
# ('a KEEP_PIN sweep must cover "at least 8 shared fixtures"'). Minimum 4
# chars so quoted articles and flags stay out.
_DQUOTE_SPAN = re.compile(r'"([^"\n]{4,})"')
_IDENTIFIER = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")
_PATHLIKE = re.compile(rf"^[\w.-]*(?:/[\w.-]+)*\.(?:{_EXTENSIONS})$")
# Inline (non-anchored) form of _PATHLIKE for masking paths mid-line, plus
# a slashless form so an unquoted bare filename never leaks its stem into
# the identifier harvest as a required anchor.
_PATHLIKE_INLINE = re.compile(rf"[\w.-]+(?:/[\w.-]+)+\.(?:{_EXTENSIONS})")
_BARE_FILENAME = re.compile(rf"\b[\w.-]+\.(?:{_EXTENSIONS})\b")
_NUMERIC_SPAN = re.compile(r"^\d+(?:-\d+)?$")


def _strip_prose_decorations(text: str) -> str:
    """Drop trailing punctuation an anchor picked up from prose."""
    return text.strip().strip(".,:;()[]{}'\"")


def _span_anchor(span: str, citation_text: str) -> str | None:
    """Return a quoted span as an anchor, or None when it is not one.

    The citation itself (or a span containing it), path-shaped spans, bare
    numeric ranges, and CLI flags are not anchors. A short span that is
    merely a substring of the cited path still is one: `model` is a real
    anchor even though the letters appear inside check_model_pins.py's own
    name.
    """
    candidate = _strip_prose_decorations(span)
    if not candidate or len(candidate) < 3 or citation_text in candidate:
        return None
    if _PATHLIKE.match(candidate) or _NUMERIC_SPAN.match(candidate):
        return None
    if candidate.startswith("-") or _CITATION.search(candidate):
        return None
    return candidate


def _anchor_candidates(context_lines: list[str], citation_text: str) -> list[str]:
    """Extract anchor strings the citing text names near a citation.

    ``context_lines`` is the citing line with its immediate neighbors.
    An anchor is text the author asserts lives at the cited location:
    a backtick span, an underscore identifier, or (handled by the
    caller) an indented continuation quote. Paths, URLs, bare numeric
    spans, CLI flags, and the citation itself are never anchors.
    """
    anchors: list[str] = []
    for line in context_lines:
        masked = _URL.sub(" ", line)
        # Triple-quote delimiters would otherwise pair with the opening
        # quote of a real anchor and swallow it.
        masked = masked.replace('"""', " ").replace("'''", " ")
        for span in _BACKTICK_SPAN.findall(masked) + _DQUOTE_SPAN.findall(masked):
            candidate = _span_anchor(span, citation_text)
            if candidate is not None:
                anchors.append(candidate)
        # Mask spans and citations before harvesting bare identifiers so a
        # path segment such as model_pin_manifest never reads as an anchor.
        masked = _BACKTICK_SPAN.sub(" ", masked)
        masked = _DQUOTE_SPAN.sub(" ", masked)
        masked = _CITATION.sub(" ", masked)
        masked = _PATHLIKE_INLINE.sub(" ", masked)
        masked = _BARE_FILENAME.sub(" ", masked)
        for identifier in _IDENTIFIER.findall(masked):
            if len(identifier) >= 5:
                anchors.append(identifier)
    seen: set[str] = set()
    unique: list[str] = []
    for anchor in anchors:
        if anchor not in seen:
            seen.add(anchor)
            unique.append(anchor)
    return unique


def _anchor_matches(anchor: str, cited_text: str) -> bool:
    """Return whether an anchor is satisfied by the cited text.

    Both sides are whitespace-normalized so a quoted contract that wraps
    across lines in either file still matches. Prose also qualifies names
    the source never spells (``mod.func`` for a file that only says
    ``def func``), so a dotted anchor matches on its final segment too.
    """
    normalized_anchor = " ".join(anchor.split())
    normalized_text = " ".join(cited_text.split())
    if normalized_anchor in normalized_text:
        return True
    if "." in normalized_anchor:
        tail = normalized_anchor.rsplit(".", 1)[-1]
        return len(tail) >= 3 and tail in normalized_text
    return False


# An ATX heading per CommonMark: up to 3 leading spaces (4 is a code
# block), optional blockquote markers, 1-6 hashes, then whitespace or end
# of line. This is what "#hashtag" and 7-hash paragraphs fail and a
# blockquoted "> ## heading" passes; the bare hash-prefix predicate below
# stays the code-comment classifier.
_ATX_HEADING = re.compile(r"^ {0,3}(?:> ?)*#{1,6}(?:[ \t]|$)")


def _atx_heading(line: str) -> bool:
    """Return whether a line is a Markdown ATX heading (blockquotes included)."""
    return bool(_ATX_HEADING.match(line))


def _hash_prefixed(line: str) -> bool:
    """Return whether a line's first non-blank character is a hash marker."""
    return line.lstrip().startswith("#")


def _indent_width(line: str) -> int:
    """Return the leading-whitespace width after any comment marker."""
    prefix = 0
    while prefix < len(line) and line[prefix] in " \t":
        prefix += 1
    if line[prefix : prefix + 1] == "#":
        rest = line[prefix + 1 :]
        return prefix + 1 + (len(rest) - len(rest.lstrip(" \t")))
    return prefix


def _continuation_quote(citing_lines: list[str], line_index: int) -> str | None:
    """Return the next line's quoted contract when it is indented deeper.

    The model_pin_manifest docstring shape PR #5336 repaired: the citation
    line ends with a colon and the following line indents a verbatim quote
    of the cited contract. That quote is the strongest anchor available,
    so harvest it.
    """
    current = citing_lines[line_index]
    # The documented shape: the citation line introduces the quote with a
    # trailing colon. Without it, a nearby indented block is unrelated code
    # and must not become an anchor this citation is judged against.
    if not current.rstrip().endswith(":"):
        return None
    # Markdown requires a blank line before an indented block, so skip
    # whitespace-only lines (bounded) before reading the candidate quote.
    following: str | None = None
    for offset in range(1, 4):
        index = line_index + offset
        if index >= len(citing_lines):
            return None
        if citing_lines[index].strip():
            following = citing_lines[index]
            break
    if following is None:
        return None
    body = following.lstrip(" \t").lstrip("#").strip()
    if len(body) < 3:
        return None
    if _indent_width(following) <= _indent_width(current):
        return None
    if _NUMERIC_SPAN.match(body) or _PATHLIKE.match(body):
        return None
    return body


# The documented marker form is "citation-freshness: ignore -- <reason>";
# a bare marker is a reasonless bypass and does not count.


def _sentence_continues(line: str) -> bool:
    """A neighbor joins the citation's sentence unless it ends one."""
    stripped = line.rstrip()
    return bool(stripped.strip()) and not stripped.endswith((".", "!", "?"))


def _context_lines(
    citing_lines: list[str] | None,
    line_index: int,
    line_text: str,
    segment: str,
    markdown: bool = False,
) -> list[str]:
    """Return this citation's slice of its line plus wrapped-sentence neighbors.

    Neighbors join only while the sentence plausibly continues across the
    wrap (the PR #5327/#5336 corpus shapes). A neighbor that finishes its
    own sentence, or a citation line that finishes one, contributes no
    anchors, so an unrelated identifier on a finished neighboring sentence
    never becomes an assertion about this citation. Wrap decisions read the
    full line; anchor harvest reads only this citation's segment of it.
    """
    context = [segment]
    if citing_lines is None:
        return context
    if markdown and _atx_heading(line_text):
        # A Markdown heading is a complete unit: it never wraps into any
        # neighbor, another heading included (an equal-prefix rule would
        # let adjacent headings pool anchors).
        return context
    own_indent = _indent_width(line_text)
    own_hash = _hash_prefixed(line_text)

    def _blocks(neighbor: str) -> bool:
        # In Markdown only a real heading is a hash boundary, so a
        # hashtag paragraph stays ordinary body text; in code files a
        # comment marker must match on both sides, so comment lines
        # continue into comment lines and never into code.
        if markdown:
            return _atx_heading(neighbor)
        return _hash_prefixed(neighbor) != own_hash

    for offset in (1, 2):
        index = line_index - offset
        if index < 0 or not _sentence_continues(citing_lines[index]):
            break
        # A deeper-indented neighbor is an example or verbatim block
        # belonging to an earlier line (a sibling citation's continuation
        # quote, say), not this sentence wrapping across lines.
        if _indent_width(citing_lines[index]) > own_indent:
            break
        if _blocks(citing_lines[index]):
            break
        context.insert(0, citing_lines[index])
    if _sentence_continues(line_text) and line_index + 1 < len(citing_lines):
        following = citing_lines[line_index + 1]
        if _indent_width(following) <= own_indent and not _blocks(following):
            context.append(following)
    return context


def _snap_out_of_tokens(text: str, point: int) -> int:
    """Move a split point out of any span, quote, or identifier it bisects."""
    for pattern in (_BACKTICK_SPAN, _DQUOTE_SPAN, _IDENTIFIER):
        for match in pattern.finditer(text):
            if match.start() < point < match.end():
                left = point - match.start()
                right = match.end() - point
                return match.start() if left <= right else match.end()
    return point


def _gap_split(line: str, prev_end: int, next_start: int) -> int:
    """Split the gap between two citations near its midpoint, whole tokens only."""
    gap = line[prev_end:next_start]
    point = len(gap) // 2
    for _ in range(3):
        snapped = _snap_out_of_tokens(gap, point)
        if snapped == point:
            break
        point = snapped
    return prev_end + point


def _same_line_segment(line: str, matches: list[re.Match[str]], index: int) -> str:
    """Return the slice of the citation line owned by one citation.

    Text between two citations binds to the nearer one (a midpoint split,
    snapped so it never bisects a span, quote, or identifier), so an anchor
    written beside one citation is never pooled into a sibling citation's
    check on the same line. Neighbor lines stay shared: a wrapped sentence's
    anchor legitimately serves every citation it describes.
    """
    if len(matches) == 1:
        return line
    if index == 0:
        start = 0
    else:
        start = _gap_split(line, matches[index - 1].end(), matches[index].start())
    if index == len(matches) - 1:
        end = len(line)
    else:
        end = _gap_split(line, matches[index].end(), matches[index + 1].start())
    return line[start:end]
