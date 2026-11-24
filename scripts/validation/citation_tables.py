"""GFM table detection for the citation-freshness gate.

A Markdown table row is a complete unit for citation anchors, so the gate
must know which lines are rows. GFM decides that per block, not per line:
a header row and a delimiter row with equal cell counts open a table, the
leading pipe is optional, and the block may sit inside a blockquote.
"""

from __future__ import annotations

import re

# Blockquote markers before a line's content: each `>` may follow up to 3
# spaces and take one optional space of its own.
_QUOTE_MARKERS = re.compile(r"^(?: {0,3}> ?)*")
# A GFM table delimiter cell: dashes with optional alignment colons.
_DELIMITER_CELL = re.compile(r"^\s*:?-+:?\s*$")
_CELL_PIPE = re.compile(r"(?<!\\)\|")


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


def _opens_table(header: str, delimiter: str) -> bool:
    """Return whether two bodies are a GFM table header and delimiter row."""
    # Four columns of indent make an indented code block, not a table.
    if header.startswith(("    ", "\t")):
        return False
    head_cells = _table_cells(header)
    delim_cells = _table_cells(delimiter)
    if head_cells is None or delim_cells is None:
        return False
    if not all(_DELIMITER_CELL.match(cell) for cell in delim_cells):
        return False
    return len(head_cells) == len(delim_cells)


def table_row(lines: list[str], index: int) -> bool:
    """Return whether a line is a row of a GFM table, header and delimiter included.

    A table is a block: a header row and a delimiter row with equal cell
    counts open it, and a blank line or a change in blockquote depth ends
    it. The leading pipe is optional, and the block may sit inside a
    blockquote. A line that only starts with `|` is prose when no header
    and delimiter pair opens its block, so it still wraps like prose.
    """
    depth, body = _quote_split(lines[index])
    if not body.strip():
        return False
    start = index
    while start > 0:
        above_depth, above_body = _quote_split(lines[start - 1])
        if above_depth != depth or not above_body.strip():
            break
        start -= 1
    # The opening delimiter row sits at most one line below this one (when
    # this line is the header) and at least one line below the block start.
    last = index + 1
    if last < len(lines):
        below_depth, below_body = _quote_split(lines[last])
        if below_depth != depth or not below_body.strip():
            last = index
    else:
        last = index
    for delimiter_index in range(last, start, -1):
        header = _quote_split(lines[delimiter_index - 1])[1]
        delimiter = _quote_split(lines[delimiter_index])[1]
        if _opens_table(header, delimiter):
            return True
    return False
