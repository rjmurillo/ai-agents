"""Anchor set of a markdown file, as GitHub and markdownlint MD051 compute it.

Canonical source: markdownlint ``lib/md051.mjs`` (``convertHeadingToHTMLFragment``
and the duplicate counter in ``MD051``). The slug rule it applies to the text
of a heading is, in order: lowercase; drop every character that is not a
Unicode Letter, Mark, Number, Connector_Punctuation, hyphen, or space; turn
each space into a hyphen. A second heading with the same slug also registers
``slug-1``, a third ``slug-2``, and so on. ``<a id>`` and ``<a name>`` tags
register their value, and ``{#custom-id}`` in a heading registers ``custom-id``.

Different than canonical: markdownlint reads a micromark token tree and this
module reads one line at a time with regular expressions. The heading text is
reduced to what micromark keeps as data: image alt text is dropped, link text
is kept without its destination, code span text is kept without backticks,
inline HTML tags and character references are dropped, and ``_emphasis_``
underscores are dropped while intraword underscores stay. Setext headings are
recognized for a single text line. A heading inside a blockquote or list item
is not recognized.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

from md_link_parse import _live_lines, mask_inline_code

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.hook_utilities.frontmatter_block import (
    FM_BOUNDARY,
    split_frontmatter,
)

_ATX = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(?P<text>.*?))?(?:[ \t]+#+)?[ \t]*$")
_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
_NOT_SETEXT_TEXT = re.compile(r"^\s*(?:[-*+>|#]|\d+[.)]\s|<|\[[^\]]+\]:)")
_IMAGE = re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])")
_LINK = re.compile(r"\[(?P<text>[^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")
_CODE_SPAN = re.compile(r"(?P<ticks>`+)(?P<body>(?:(?!(?P=ticks)).)+?)(?P=ticks)")
_HTML_TAG = re.compile(r"<[^>\n]*>")
_CHAR_REF = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_EMPHASIS_UNDERSCORE = re.compile(r"(?<!\w)(?P<run>_{1,2})(?=\S)(?P<body>.+?)(?<=\S)(?P=run)(?!\w)")
_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
_CUSTOM_ID = re.compile(r"\{(#[a-z\d]+(?:[-_]+[a-z\d]+)*)\}")
_HTML_ID = re.compile(r"\sid\s*=\s*[\"']?([^\"'\s>]+)")
_HTML_NAME = re.compile(r"\sname\s*=\s*[\"']?([^\"'\s>]+)")
_HTML_OPEN_TAG = re.compile(r"<(?P<name>[A-Za-z][A-Za-z0-9]*)(?P<attrs>[^>]*)>")
_KEPT_MAJOR = frozenset("LMN")  # Letter, Mark, Number; Connector_Punctuation is "Pc"


def heading_text(raw: str) -> str:
    """Reduce heading markdown to the text GitHub slugs, mirroring MD051."""
    # Stash code spans first. Link syntax inside a code span is literal text,
    # so removing destinations before this pass turns `` `[x](y)` `` into `x`.
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(match.group("body").strip(" ") or match.group("body"))
        return f"\x00{len(spans) - 1}\x00"

    text = _CODE_SPAN.sub(stash, raw)
    text = _IMAGE.sub("", text)
    text = _LINK.sub(lambda m: m.group("text"), text)
    text = _HTML_TAG.sub("", text)
    text = _CHAR_REF.sub("", text)
    text = _EMPHASIS_UNDERSCORE.sub(lambda m: m.group("body"), text)
    text = _ESCAPE.sub(lambda m: m.group(1), text)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


def slugify(text: str) -> str:
    """Return the GitHub fragment (without ``#``) for already-reduced heading text."""
    kept = "".join(
        ch
        for ch in text.lower()
        if ch in "- "
        or unicodedata.category(ch)[0] in _KEPT_MAJOR
        or unicodedata.category(ch) == "Pc"
    )
    return kept.replace(" ", "-")


def _frontmatter_end(text: str) -> int:
    """Return the 1-indexed line of the closing fence of YAML frontmatter, or 0.

    The fence comes from ``scripts/hook_utilities/frontmatter_block.py``.
    """
    split = split_frontmatter(text)
    opening = FM_BOUNDARY.match(text)
    if not split.found or opening is None:
        return 0
    closing_start = opening.end() + len(split.raw)
    return len(text[:closing_start].splitlines()) + 1


def _heading_texts(body: str) -> list[str]:
    """Return the raw text of every ATX and setext heading outside fences."""
    skip_through = _frontmatter_end(body)
    live = [(n, line) for n, line in _live_lines(body) if n > skip_through]
    by_number = dict(live)
    headings: list[str] = []
    for number, line in live:
        atx = _ATX.match(line)
        if atx:
            headings.append(atx.group("text") or "")
            continue
        underline = by_number.get(number + 1)
        if (
            underline is not None
            and _SETEXT_UNDERLINE.match(underline)
            and line.strip()
            and not _SETEXT_UNDERLINE.match(line)
            and not _NOT_SETEXT_TEXT.match(line)
        ):
            headings.append(line.strip())
    return headings


def _html_anchors(body: str) -> set[str]:
    """Return ``id`` values on any tag and ``name`` values on ``<a>`` tags."""
    anchors: set[str] = set()
    for _, line in _live_lines(body):
        # A tag inside backticks is an example, not an anchor.
        for tag in _HTML_OPEN_TAG.finditer(mask_inline_code(line, links_only=False)):
            attrs = " " + tag.group("attrs")
            found = _HTML_ID.search(attrs)
            if found is None and tag.group("name").lower() == "a":
                found = _HTML_NAME.search(attrs)
            if found:
                anchors.add(found.group(1))
    return anchors


def anchors_in(body: str) -> set[str]:
    """Return every fragment (without ``#``) a link into this file may use."""
    fragments: dict[str, int] = {"top": 0}
    for raw in _heading_texts(body):
        slug = slugify(heading_text(raw))
        if not slug:
            continue
        seen = fragments.get(slug, 0)
        if seen:
            fragments[f"{slug}-{seen}"] = 0
        fragments[slug] = seen + 1
        for custom in _CUSTOM_ID.findall(raw):
            fragments.setdefault(custom[1:], 1)
    return set(fragments) | _html_anchors(body)
