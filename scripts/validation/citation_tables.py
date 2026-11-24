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
# Block starts that end a table (and the paragraph before it) in GFM: an
# ATX heading, a code fence, a thematic break, or a list item.
_INTERRUPTER = re.compile(
    r"""^\ {0,3}(?:
        \#{1,6}(?:[\ \t]|$)              # ATX heading
        | `{3,} | ~{3,}                  # code fence
        | (?:(?:-[\ \t]*){3,}|(?:\*[\ \t]*){3,}|(?:_[\ \t]*){3,})$  # thematic break
        | (?:[-+*]|\d{1,9}[.)])(?:[\ \t]|$)  # list item
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


def _in_block(depth: int, line: str) -> bool:
    """Return whether a line continues a block at this blockquote depth."""
    line_depth, body = _quote_split(line)
    return line_depth == depth and bool(body.strip()) and not _interrupts(body)


def table_row(lines: list[str], index: int) -> bool:
    """Return whether a line is a row of a GFM table, header and delimiter included.

    A table is a block: a header row and a delimiter row with equal cell
    counts open it. A blank line, a change in blockquote depth, or another
    block start (heading, fence, thematic break, list item) ends it. The
    leading pipe is optional, and the block may sit inside a blockquote.
    A line that only starts with `|` is prose when no header and delimiter
    pair opens its block, so it still wraps like prose.

    Each call walks back to its block start, so the cost per call is the
    block length. Blocks end at blank lines, which keeps that short.
    """
    depth = _quote_split(lines[index])[0]
    if not _in_block(depth, lines[index]):
        return False
    start = index
    while start > 0 and _in_block(depth, lines[start - 1]):
        start -= 1
    # Candidate delimiter rows run from one line below the block start up to
    # one line below this line, the case where this line is the header.
    max_delimiter = index
    if index + 1 < len(lines) and _in_block(depth, lines[index + 1]):
        max_delimiter = index + 1
    for delimiter_index in range(max_delimiter, start, -1):
        header = _quote_split(lines[delimiter_index - 1])[1]
        delimiter = _quote_split(lines[delimiter_index])[1]
        if _opens_table(header, delimiter):
            return True
    return False
