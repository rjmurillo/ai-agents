"""GFM table detection for the citation-freshness gate.

A Markdown table row is a complete unit for citation anchors, so the gate
must know which lines are rows. GFM decides that per block, not per line:
a header row and a delimiter row with equal cell counts open a table, the
leading pipe is optional, and the block may sit inside a blockquote.

Known limit: a table nested under a list item by four or more columns of
indent reads as an indented code block here, so it is not detected.
"""

from __future__ import annotations

import re

# Blockquote markers before a line's content: each `>` may follow up to 3
# spaces and take one optional space of its own.
_QUOTE_MARKERS = re.compile(r"^(?: {0,3}> ?)*")
# A GFM table delimiter cell: dashes with optional alignment colons.
_DELIMITER_CELL = re.compile(r"^\s*:?-+:?\s*$")
_CELL_PIPE = re.compile(r"(?<!\\)\|")
# Block starts that end a table in GFM: an ATX heading (the blockquote-free
# form of citation_anchors._ATX_HEADING), a code fence (a backtick fence's
# info string holds no backtick, so a row opening with ```x``` stays a row),
# a thematic break, a list item, or an HTML block of GFM types 1 to 6.
_INTERRUPTER = re.compile(
    r"""^\ {0,3}(?:
        \#{1,6}(?:\s|$)
        | `{3,}[^`]*$ | ~{3,}
        | (?:(?:-[\ \t]*){3,}|(?:\*[\ \t]*){3,}|(?:_[\ \t]*){3,})\s*$
        | (?:[-+*]|\d{1,9}[.)])(?:\s|$)
        | (?i:<(?:script|pre|style|textarea)(?:\s|>|$))
        | <!-- | <\? | <![A-Za-z] | <!\[CDATA\[
        | (?i:</?(?:address|article|aside|base|basefont|blockquote|body|caption|center
            |col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure
            |footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li
            |link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search
            |section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)
            (?:\s|/?>|$))
    )""",
    re.VERBOSE,
)


def _quote_split(line: str) -> tuple[int, str]:
    """Return a line's blockquote depth and the content after its markers."""
    markers = _QUOTE_MARKERS.match(line)
    prefix = markers.group(0) if markers else ""
    return prefix.count(">"), line[len(prefix) :]


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
    """Return a delimiter row's cells, or None when the body is not one."""
    cells = _table_cells(body)
    if cells is None or not all(_DELIMITER_CELL.match(cell) for cell in cells):
        return None
    return cells


def _opens_table(header: str, delimiter: str) -> bool:
    """Return whether two bodies are a GFM table header and delimiter row."""
    # Four columns of indent make an indented code block, not a table.
    if header.startswith(("    ", "\t")) or _interrupts(header):
        return False
    head_cells = _table_cells(header)
    delim_cells = _delimiter_cells(delimiter)
    if head_cells is None or delim_cells is None:
        return False
    return len(head_cells) == len(delim_cells)


def _interrupts(body: str) -> bool:
    """Return whether a body starts a block that ends any table above it."""
    # "- | -" is a valid delimiter row, not a list item.
    return bool(_INTERRUPTER.match(body)) and _delimiter_cells(body) is None


def _table_rows(lines: list[str]) -> list[bool]:
    """Classify every line in one pass: True where it is a GFM table row."""
    split = [_quote_split(line) for line in lines]
    open_line = [bool(body.strip()) and not _interrupts(body) for _, body in split]
    rows = [False] * len(lines)
    start = 0
    while start < len(lines):
        if not open_line[start]:
            start += 1
            continue
        depth = split[start][0]
        end = start
        while end + 1 < len(lines) and open_line[end + 1] and split[end + 1][0] == depth:
            end += 1
        # The first header and delimiter pair opens the table, which then
        # runs to the end of the block.
        for delimiter in range(start + 1, end + 1):
            if _opens_table(split[delimiter - 1][1], split[delimiter][1]):
                rows[delimiter - 1 : end + 1] = [True] * (end - delimiter + 2)
                break
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
    block start (heading, fence, thematic break, list item, HTML block) ends
    it. The leading pipe is optional, and the block may sit inside a
    blockquote. A line that only starts with `|` is prose when no header and
    delimiter pair opens its block, so it still wraps like prose.

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
