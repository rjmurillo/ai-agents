"""GFM table detection for the citation-freshness gate.

A Markdown table row is a complete unit for citation anchors, so the gate
must know which lines are rows. GFM decides that per block, not per line:
a header row and a delimiter row with equal cell counts open a table, the
leading pipe is optional, and the block may sit inside a blockquote or a
list item. A table never opens inside fenced code or a raw HTML block.

Known limits: a list item nests at most `_MAX_MARKERS` markers on one line, and
a blockquote inside a list item (or the reverse) ends the inner container at
the quote-depth change. A table indented four or more columns past its
container reads as an indented code block, so it is not detected.

GFM reads a lazy continuation line (an unindented line that continues a list
or quote paragraph) as part of that paragraph. This module reads it as a new
line outside the container. A header that follows other paragraph lines, and a
body row indented four or more columns, can also differ from cmark-gfm. Over
all tracked Markdown files the table counts agree with cmark-gfm. Over
synthetic documents of up to five block-start lines they do not always agree.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# Blockquote markers before a line's content: each `>` may follow up to 3
# spaces and take one optional space of its own.
_QUOTE_MARKER = re.compile(r" {0,3}> ?")
_QUOTE_MARKERS = re.compile(r"^(?: {0,3}> ?)*")
_LEADING_WHITESPACE = re.compile(r"^[ \t]*")
# A GFM table delimiter cell: dashes with optional alignment colons.
_DELIMITER_CELL = re.compile(r"^\s*:?-+:?\s*$")
_CELL_PIPE = re.compile(r"(?<!\\)\|")
# A thematic break. Beats a list item on `- - -` and `* * *`.
_BREAK = re.compile(
    r"^\ {0,3}(?:-(?:[\ \t]*-){2,}|\*(?:[\ \t]*\*){2,}|_(?:[\ \t]*_){2,})[\ \t\r]*$"
)
# A list item marker, then either content (after any run of spaces or tabs)
# or the end of the line. A no-break space is content, not a gap.
_LIST_ITEM = re.compile(r"^(?P<marker>[-+*]|\d{1,9}[.)])(?:(?P<gap>[ \t]+)(?=\S)|[ \t\r]*$)")
# One marker per list nesting level, capped so a hostile `- - - - ...` line
# costs a bounded number of slices.
_MAX_MARKERS = 8
# A fence opener, and its closer. A backtick fence's info string holds no
# backtick, so a row opening with ```x``` stays a row.
_FENCE_OPEN = re.compile(r"^ {0,3}(?:(?P<tick>`{3,})[^`]*|(?P<tilde>~{3,}).*)$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})[ \t\r]*$")
# Block starts that end a table in GFM and are not raw HTML: an ATX heading
# (the blockquote-free form of citation_anchors._ATX_HEADING) or a thematic
# break. A list item and a fence are handled before this pattern runs.
_INTERRUPTER = re.compile(
    r"""^\ {0,3}(?:
        \#{1,6}(?:[\ \t\r]|$)
        | (?:-(?:[\ \t]*-){2,}|\*(?:[\ \t]*\*){2,}|_(?:[\ \t]*_){2,})[\ \t\r]*$
    )""",
    re.VERBOSE,
)
# Raw HTML blocks of GFM types 1 to 5: a start pattern and the strings that
# end the block, lowercase. GFM ends one at the first line that contains an end
# string, so a plain substring test is the whole rule (`--!>` does not end a
# comment). The block runs through blank lines to that line, which may be the
# opener's own.
_HTML_RAW = (
    (
        re.compile(r"(?i)^ {0,3}<(?:script|pre|style|textarea)(?:\s|>|$)"),
        ("</script>", "</pre>", "</style>", "</textarea>"),
    ),
    (re.compile(r"^ {0,3}<!--"), ("-->",)),
    (re.compile(r"^ {0,3}<\?"), ("?>",)),
    (re.compile(r"^ {0,3}<![A-Za-z]"), (">",)),
    (re.compile(r"^ {0,3}<!\[CDATA\["), ("]]>",)),
)
# Type 6: a block-level tag name. The block ends at a blank line.
_HTML_BLOCK = re.compile(
    r"""^\ {0,3}(?i:</?(?:address|article|aside|base|basefont|blockquote|body|caption|center
        |col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure
        |footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li
        |link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search
        |section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)
        (?:\s|/?>|$))""",
    re.VERBOSE,
)
# Type 7: one complete open or closing tag alone on its line. It cannot
# interrupt a paragraph, but it ends a table and opens a block after a blank
# line. Each attribute starts with a gap and holds no nested quantifier on
# the same characters, so a hostile line scans in linear time.
_ATTRIBUTE = (
    r"""[ \t]+[A-Za-z_:][A-Za-z0-9_.:-]*"""
    r"""(?:[ \t]*=[ \t]*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?"""
)
_HTML_TAG = re.compile(
    r"^ {0,3}(?:<(?!(?i:script|style|pre|textarea)(?![A-Za-z0-9-]))[A-Za-z][A-Za-z0-9-]*"
    rf"(?:{_ATTRIBUTE})*[ \t]*/?>"
    r"|</(?!(?i:script|style|pre|textarea)(?![A-Za-z0-9-]))[A-Za-z][A-Za-z0-9-]*[ \t]*>)"
    r"[ \t\r]*$"
)


class _Item(NamedTuple):
    """An open list item: its identity, quote depth, and content column."""

    ident: int
    depth: int
    offset: int


class _Raw(NamedTuple):
    """An open fence or raw HTML block, and the container it sits in."""

    depth: int
    item: int
    fence: str  # the opener's fence characters; empty for raw HTML
    end: tuple[str, ...] | None  # raw HTML types 1 to 5; None ends at a blank line


class _Unit(NamedTuple):
    """One line a table can contain: its container and its text inside it."""

    key: tuple[int, int]  # (quote depth, list item identity)
    body: str


def _quote_split(line: str, limit: int | None = None) -> tuple[int, str]:
    """Return a line's blockquote depth and the content after its markers.

    With a limit, strip at most that many markers: an open fence or raw HTML
    block owns every `>` past its own quote depth as content.
    """
    if limit is None:
        markers = _QUOTE_MARKERS.match(line)
        prefix = markers.group(0) if markers else ""
        return prefix.count(">"), line[len(prefix) :]
    pos = depth = 0
    while depth < limit and (marker := _QUOTE_MARKER.match(line, pos)):
        pos, depth = marker.end(), depth + 1
    return depth, line[pos:]


def _expand_leading_tabs(body: str) -> str:
    """Turn a line's leading tabs into spaces so indent is a column count."""
    lead = _LEADING_WHITESPACE.match(body)
    prefix = lead.group(0) if lead else ""
    return prefix.expandtabs(4) + body[len(prefix) :] if "\t" in prefix else body


def _split_line(line: str, limit: int | None = None) -> tuple[int, str]:
    """Return a line's quote depth and its content with leading tabs expanded."""
    depth, body = _quote_split(line, limit)
    return depth, _expand_leading_tabs(body)


def _table_cells(body: str) -> list[str] | None:
    """Split a table-shaped body into cells, or return None without a pipe."""
    text = body.strip()
    if not _CELL_PIPE.search(text):
        return None
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return _CELL_PIPE.split(text)


def _delimiter_cells(body: str) -> list[str] | None:
    """Return a delimiter row's cells, or None when the body is not one.

    A one-cell delimiter may drop its pipes, but only with an alignment
    colon: bare dashes are a setext underline or a thematic break.
    """
    cells = _table_cells(body)
    if cells is None:
        text = body.strip()
        cells = [text] if ":" in text else None
    if cells is None or not all(_DELIMITER_CELL.match(cell) for cell in cells):
        return None
    return cells


def _header_cells(body: str, delimiter_cells: list[str]) -> list[str] | None:
    """Return a header row's cells, or None when the body cannot be one.

    A one-cell header may drop its pipes when the delimiter has one cell.
    """
    cells = _table_cells(body)
    if cells is None and len(delimiter_cells) == 1 and body.strip():
        return [body.strip()]
    return cells


def _opens_table(header: str, delimiter: str) -> bool:
    """Return whether two bodies are a GFM table header and delimiter row."""
    # Four columns of indent make an indented code block, not a table.
    if header.startswith(("    ", "\t")) or delimiter.startswith(("    ", "\t")):
        return False
    delim_cells = _delimiter_cells(delimiter)
    if delim_cells is None:
        return False
    head_cells = _header_cells(header, delim_cells)
    return head_cells is not None and len(head_cells) == len(delim_cells)


def _html_start(body: str, paragraph_open: bool) -> tuple[bool, tuple[str, ...] | None, bool]:
    """Classify a body as a raw HTML block start.

    Returns whether the body starts one, the strings that end it (None for
    types 6 and 7, which end at a blank line), and whether the block runs past
    this line. Type 7 cannot interrupt a paragraph, so `paragraph_open`
    blocks it.
    """
    for start, end in _HTML_RAW:
        match = start.match(body)
        if match:
            return True, end, not _has_end(body[match.end() :], end)
    if _HTML_BLOCK.match(body) or (not paragraph_open and _HTML_TAG.match(body)):
        return True, None, True
    return False, None, False


class _Scanner:
    """Walk a file once, tracking the containers and raw blocks a line is in."""

    def __init__(self) -> None:
        self._items: list[_Item] = []
        self._raw: _Raw | None = None
        self._next_ident = 1
        self._prev_key: tuple[int, int] | None = None

    def unit(self, line: str) -> _Unit | None:
        """Return a line as a table candidate, or None when it ends any table."""
        raw = self._raw
        depth, body = _split_line(line, raw.depth if raw else None)
        blank = not body.strip()
        self._leave_items(depth, body, blank)
        if raw and self._in_raw(depth, body, blank):
            self._prev_key = None
            return None
        if raw:
            # The raw block ended on this line, so its quote cap no longer applies.
            depth, body = _split_line(line)
            blank = not body.strip()
            self._leave_items(depth, body, blank)
        inner = body if blank else self._enter_items(body, depth)
        key = (depth, self._owner())
        if not inner.strip() or self._starts_block(inner, depth, key):
            self._prev_key = None
            return None
        self._prev_key = key
        return _Unit(key, inner)

    def _owner(self) -> int:
        """Return the identity of the innermost open list item, 0 for none."""
        return self._items[-1].ident if self._items else 0

    def _base(self) -> int:
        """Return the column where the innermost open list item's content starts."""
        return self._items[-1].offset if self._items else 0

    def _leave_items(self, depth: int, body: str, blank: bool) -> None:
        """Close list items a dedent or a change of quote depth ends."""
        indent = len(body) - len(body.lstrip(" "))
        while self._items and (
            self._items[-1].depth != depth or (not blank and indent < self._base())
        ):
            self._items.pop()

    def _enter_items(self, body: str, depth: int) -> str:
        """Open the list items a line starts and return the text after them."""
        rest = body[self._base() :]
        for _ in range(_MAX_MARKERS):
            indent = len(rest) - len(rest.lstrip(" "))
            marker = _LIST_ITEM.match(rest.lstrip(" "))
            if (
                indent >= 4
                or marker is None
                or _BREAK.match(rest)
                or _delimiter_cells(rest) is not None
            ):
                return rest
            gap = len(marker.group("gap") or "")
            width = indent + len(marker.group("marker")) + (gap if 1 <= gap <= 4 else 1)
            self._items.append(_Item(self._next_ident, depth, self._base() + width))
            self._next_ident += 1
            rest = rest[width:]
        return rest

    def _in_raw(self, depth: int, body: str, blank: bool) -> bool:
        """Consume a line that stays inside the open fence or raw HTML block."""
        raw = self._raw
        if raw is None:
            return False
        owner_open = raw.item == 0 or any(item.ident == raw.item for item in self._items)
        if depth < raw.depth or not owner_open:
            self._raw = None
            return False
        if blank:
            if raw.end is None and not raw.fence:
                self._raw = None
            return True
        inner = body[self._base() :]
        if raw.fence:
            closer = _FENCE_CLOSE.match(inner) if depth == raw.depth else None
            if closer and _closes(closer.group("fence"), raw.fence):
                self._raw = None
        elif raw.end is not None and _has_end(inner, raw.end):
            self._raw = None
        return True

    def _starts_block(self, inner: str, depth: int, key: tuple[int, int]) -> bool:
        """Open a fence or raw HTML block, or report another block start."""
        fence = _FENCE_OPEN.match(inner)
        if fence:
            opener = fence.group("tick") or fence.group("tilde")
            self._raw = _Raw(depth, self._owner(), opener, None)
            return True
        started, end, stays_open = _html_start(inner, self._prev_key == key)
        if started:
            self._raw = _Raw(depth, self._owner(), "", end) if stays_open else None
            return True
        return bool(_INTERRUPTER.match(inner))


def _has_end(text: str, end: tuple[str, ...]) -> bool:
    """Return whether a line contains one of a raw HTML block's end strings."""
    lowered = text.lower()
    return any(marker in lowered for marker in end)


def _closes(closer: str, opener: str) -> bool:
    """Return whether a fence line closes an opener: same character, no shorter."""
    return closer[0] == opener[0] and len(closer) >= len(opener)


def _mark_table(units: list[_Unit | None], rows: list[bool], start: int, end: int) -> None:
    """Mark the table in one block of units, if its first pair opens one."""
    for delimiter in range(start + 1, end + 1):
        header, delim = units[delimiter - 1], units[delimiter]
        if header is None or delim is None or not _opens_table(header.body, delim.body):
            continue
        last = end
        for index in range(delimiter + 1, end + 1):
            unit = units[index]
            if unit is not None and _HTML_TAG.match(unit.body):
                last = index - 1
                break
        rows[delimiter - 1 : last + 1] = [True] * (last - delimiter + 2)
        return


def _table_rows(lines: list[str]) -> list[bool]:
    """Classify every line in one pass: True where it is a GFM table row."""
    scanner = _Scanner()
    units = [scanner.unit(line) for line in lines]
    rows = [False] * len(lines)
    start = 0
    while start < len(lines):
        first = units[start]
        if first is None:
            start += 1
            continue
        end = start
        while end + 1 < len(lines) and (nxt := units[end + 1]) is not None and nxt.key == first.key:
            end += 1
        # The first header and delimiter pair opens the table, which then
        # runs to the end of the block.
        _mark_table(units, rows, start, end)
        start = end + 1
    return rows


# The last file classified. The gate asks about many lines of one file in a
# row, so one entry turns repeat calls into lookups. The entry holds the list
# itself, so an identity match can never point at a different, reused list.
_LAST_CLASSIFIED: list[tuple[list[str], int, list[bool]]] = []


def table_row(lines: list[str], index: int) -> bool:
    """Return whether a line is a row of a GFM table, header and delimiter included.

    A table is a block: a header row and a delimiter row with equal cell
    counts open it. A blank line, a change in blockquote depth, or another
    block start (heading, fence, thematic break, HTML block) ends it, and so
    does the end of the list item it sits in. A table never opens inside a
    fenced code block or a raw HTML block. The leading pipe is optional, and
    the block may sit inside a blockquote or a list item. A line that only
    starts with `|` is prose when no header and delimiter pair opens its
    block, so it still wraps like prose.

    The first call for a file classifies all its lines in one linear pass;
    later calls for the same list are lookups.
    """
    if not (
        _LAST_CLASSIFIED
        and _LAST_CLASSIFIED[0][0] is lines
        and _LAST_CLASSIFIED[0][1] == len(lines)
    ):
        _LAST_CLASSIFIED[:] = [(lines, len(lines), _table_rows(lines))]
    return _LAST_CLASSIFIED[0][2][index]
