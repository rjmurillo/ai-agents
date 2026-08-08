"""AST-based Markdown parsing utilities for session validation.

Provides structured extraction of Markdown tables and checklists using
markdown-it-py instead of fragile regex patterns. Simple patterns (SHAs,
dates, filenames) remain regex-based per the hybrid approach in issue #842.

Exit codes follow ADR-035 when used as a standalone script.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from markdown_it import MarkdownIt


@dataclass(frozen=True)
class ChecklistMatch:
    """Result of searching for a checklist item in a Markdown table."""

    complete: bool
    evidence: str


@dataclass
class TableRow:
    """A single parsed row from a Markdown table."""

    cells: list[str] = field(default_factory=list)


@dataclass
class ParsedTable:
    """A parsed Markdown table with headers and rows."""

    headers: list[str] = field(default_factory=list)
    rows: list[TableRow] = field(default_factory=list)


@dataclass(frozen=True)
class CellSegment:
    """One inline run inside a table cell.

    ``code`` marks a span written between backticks. A caller that treats a
    code span as documentation rather than as content has to tell the two
    apart, and only the token stream knows which is which. Keeping that
    distinction here, instead of a policy decision about which spans matter,
    leaves the policy with the caller that owns it.
    """

    content: str
    code: bool


@dataclass(frozen=True)
class TableCell:
    """A table cell's inline segments and its 1-based source line."""

    segments: tuple[CellSegment, ...]
    line: int

    @property
    def text(self) -> str:
        """The cell's rendered text, code spans included."""
        return "".join(segment.content for segment in self.segments)


@dataclass
class Section:
    """A Markdown section with heading level, title, and body content."""

    level: int
    title: str
    body: str


_FOOTNOTE_REFERENCE_RE = re.compile(r"\[\^[^\]\n]+\]")


class MarkdownNestingError(ValueError):
    """Raised when input nests past the parser's ``maxNesting`` limit.

    markdown-it stops emitting block tokens once container nesting reaches
    ``maxNesting`` and silently discards the rest of the input (see
    ``ParserBlock.tokenize``: it sets ``state.line = endLine`` and breaks). A
    code-stripping pass over a truncated token stream leaves the dropped,
    deeply-nested fenced code unblanked, so a ``vendor-portability`` marker or
    an example path hidden that deep would leak into the prose the caller
    scans. Refusing the file keeps the gate fail-closed: input the parser
    cannot fully represent is an incomplete scan, not clean prose.
    """


def _create_parser(max_nesting: int | None = None) -> MarkdownIt:
    """Create a configured markdown-it parser with table support.

    ``max_nesting`` overrides the CommonMark default only for the bounded
    second parse in :func:`_raise_if_nesting_truncated`. The primary parse keeps
    the default so its recursion stays bounded; the limit exists to stop a
    pathologically nested document from exhausting the stack, and raising it for
    the primary parse would reintroduce that denial-of-service vector.
    """
    md = MarkdownIt("commonmark").enable("table")
    if max_nesting is not None:
        md.options["maxNesting"] = max_nesting
    return md


# Block token types whose source lines are code, not prose. ``fence`` covers
# ```` ``` ```` and ``~~~`` blocks; ``code_block`` covers indented code. Both
# are resolved by the CommonMark parser, which tracks fence termination,
# blockquote depth, and list-relative indentation that a line-based scanner
# gets wrong.
_CODE_BLOCK_TOKEN_TYPES = frozenset({"fence", "code_block"})


def _block_token_shape(tokens: list) -> list:
    """Structural fingerprint of the block token stream.

    Inline nesting lives inside an ``inline`` token's ``children`` and is
    excluded here, so deeply-nested emphasis or links (which cannot hide a code
    block) do not trigger a refusal. Only block-level truncation, which changes
    which lines a code-stripping pass blanks, changes this fingerprint.
    """
    return [
        (token.type, token.tag, token.level, tuple(token.map) if token.map else None)
        for token in tokens
    ]


def _raise_if_nesting_truncated(
    markdown: str, tokens: list, md: MarkdownIt
) -> None:
    """Fail closed when the primary parse dropped content at ``maxNesting``.

    The primary token stream cannot reveal truncation on its own: markdown-it
    caps reported nesting at ``maxNesting - 1`` whether the input stopped one
    level below the limit (complete) or ran past it (truncated). A bounded
    second parse at a higher limit disambiguates. If raising the limit changes
    the block structure, the primary parse was truncated and the file is
    refused. Content nesting past the second limit diverges further still, so
    the check never passes by merely moving the cliff, and the second parse
    stays bounded so no denial-of-service vector reopens.

    The second parse runs only when the primary reached ``maxNesting - 1``. The
    committed corpus peaks at level 9, far below the limit, so this path never
    fires on real files and adds no cost to a normal scan.
    """
    if not tokens:
        return
    max_nesting = md.options["maxNesting"]
    if max(token.level for token in tokens) < max_nesting - 1:
        return
    deep = _create_parser(max_nesting * 2)
    if _block_token_shape(tokens) != _block_token_shape(deep.parse(markdown)):
        raise MarkdownNestingError(
            f"Markdown nests past the parser limit (maxNesting={max_nesting}); "
            "the document cannot be fully scanned and is refused (issue #3499)."
        )


def blank_code_block_lines(markdown: str) -> str:
    """Return ``markdown`` with fenced and indented code block lines blanked.

    Every source line that CommonMark attributes to a fenced or indented code
    block, including the fence marker lines, is replaced by an empty string.
    Line count and every non-code line are preserved, so a caller that matches
    against the result keeps stable line numbers.

    Inline code spans are left intact; strip those separately when needed.

    Any exception the parser raises propagates to the caller, which must not
    treat a parse failure as clean prose. Failing closed here is deliberate: a
    silent empty return would let an unparseable file bypass the portability
    gate. For the same reason, input that nests past the parser's ``maxNesting``
    limit raises :class:`MarkdownNestingError` rather than being scanned from a
    silently truncated token stream.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    _raise_if_nesting_truncated(markdown, tokens, md)
    lines = markdown.split("\n")
    line_count = len(lines)
    for token in tokens:
        if token.type not in _CODE_BLOCK_TOKEN_TYPES or token.map is None:
            continue
        start, end = token.map
        for index in range(max(start, 0), min(end, line_count)):
            lines[index] = ""
    return "\n".join(lines)


def _cell_text(content: str) -> str:
    """Normalize table cell text for validation consumers."""
    return _FOOTNOTE_REFERENCE_RE.sub("", content).strip()


def parse_tables(markdown: str) -> list[ParsedTable]:
    """Extract all tables from Markdown content using AST parsing.

    Args:
        markdown: Raw Markdown text.

    Returns:
        List of ParsedTable objects with headers and data rows.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    tables: list[ParsedTable] = []

    i = 0
    while i < len(tokens):
        if tokens[i].type == "table_open":
            table = _extract_table(tokens, i)
            if table is not None:
                tables.append(table)
            # Skip to table_close
            while i < len(tokens) and tokens[i].type != "table_close":
                i += 1
        i += 1

    return tables


def extract_lookup_references(markdown: str) -> list[str]:
    """Return .md targets from rendered lookup rows and table file cells."""
    md = _create_parser()
    tokens = md.parse(markdown)
    _raise_if_nesting_truncated(markdown, tokens, md)

    references: list[str] = []
    in_table = False
    in_body = False
    cell_index = -1
    source_lines = markdown.splitlines()

    for token in tokens:
        if token.type == "table_open":
            in_table = True
            continue
        if token.type == "table_close":
            in_table = False
            in_body = False
            continue
        if token.type == "tbody_open":
            in_body = True
            continue
        if token.type == "tbody_close":
            in_body = False
            continue
        if token.type == "tr_open":
            cell_index = -1
            continue
        if token.type in {"th_open", "td_open"}:
            cell_index += 1
            continue
        if token.type != "inline":
            continue

        children = token.children or []
        link_targets: list[str] = []
        for child in children:
            if child.type != "link_open":
                continue
            href = child.attrGet("href")
            if isinstance(href, str) and href.endswith(".md"):
                link_targets.append(href)
        if in_table:
            if link_targets:
                references.extend(link_targets)
            elif in_body and cell_index == 1:
                bare_target = token.content.strip()
                if bare_target:
                    references.append(
                        bare_target
                        if bare_target.endswith(".md")
                        else f"{bare_target}.md"
                    )
            continue

        if token.map is None:
            continue
        start_line, end_line = token.map
        lookup_row_present = any(
            re.match(r"^ {0,3}\|", source_lines[line_number])
            for line_number in range(
                max(start_line, 0),
                min(end_line, len(source_lines)),
            )
        )
        if lookup_row_present:
            references.extend(link_targets)

    return references


def iter_table_cell_text(markdown: str) -> Iterator[TableCell]:
    """Yield the rendered text of every table cell with its source line.

    Only cells of tables the CommonMark parser actually recognises are
    emitted, which is the point. A line-based scanner that calls any
    pipe-shaped line a table row is wrong in both directions: it misses
    tables written without outer pipes, inside a blockquote, or indented
    under a list item, and it matches pipe-shaped prose that renders as a
    paragraph because it has no delimiter row.

    Each cell is yielded as its inline segments rather than as one string, so
    a caller can decide what a code span means to it. Emphasis contributes its
    text because the emphasis markers are not part of the rendered content.
    Fenced and indented code blocks and HTML comments never parse as tables,
    so they are excluded by construction rather than by a second stripping
    pass.

    Fails closed on input the parser cannot fully represent, for the reason
    given in :class:`MarkdownNestingError`.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    _raise_if_nesting_truncated(markdown, tokens, md)

    line = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "tr_open" and token.map:
            line = token.map[0] + 1
        elif (
            token.type in ("th_open", "td_open")
            and index + 1 < len(tokens)
            and tokens[index + 1].type == "inline"
        ):
            children = tokens[index + 1].children or []
            segments = tuple(
                CellSegment(content=child.content, code=child.type == "code_inline")
                for child in children
                if child.type in ("text", "code_inline")
            )
            yield TableCell(segments=segments, line=line)
            index += 1
        index += 1


def _extract_table(tokens: list, start: int) -> ParsedTable | None:
    """Extract a single table from the token stream starting at table_open."""
    table = ParsedTable()
    i = start + 1
    in_thead = False
    in_tbody = False
    current_row: list[str] = []

    while i < len(tokens):
        token = tokens[i]
        if token.type == "table_close":
            break
        if token.type == "thead_open":
            in_thead = True
        elif token.type == "thead_close":
            in_thead = False
        elif token.type == "tbody_open":
            in_tbody = True
        elif token.type == "tbody_close":
            in_tbody = False
        elif token.type == "tr_open":
            current_row = []
        elif token.type == "tr_close":
            if in_thead:
                table.headers = current_row
            elif in_tbody:
                table.rows.append(TableRow(cells=current_row))
        elif token.type in ("th_open", "td_open"):
            # Next token is inline with cell content
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                cell_content = _cell_text(tokens[i + 1].content)
                current_row.append(cell_content)
                i += 1  # skip inline token
            else:
                current_row.append("")
        i += 1

    return table


def find_checklist_item(markdown: str, pattern: str) -> ChecklistMatch:
    """Search Markdown tables for a row matching pattern with [x] checkbox.

    Parses all tables in the document using AST, then searches for rows
    where any cell matches the pattern (case-insensitive) and another cell
    contains a checked checkbox [x].

    Args:
        markdown: Raw Markdown text containing tables.
        pattern: Regex pattern to match against cell content.

    Returns:
        ChecklistMatch with complete=True and evidence text if found.
    """
    tables = parse_tables(markdown)
    compiled = re.compile(pattern, re.IGNORECASE)

    for table in tables:
        for row in table.rows:
            has_pattern_match = False
            has_checked = False
            evidence = ""

            for cell in row.cells:
                if compiled.search(cell):
                    has_pattern_match = True
                if "[x]" in cell.lower():
                    has_checked = True

            if has_pattern_match and has_checked:
                # Evidence is the last non-checkbox, non-pattern cell
                for cell in reversed(row.cells):
                    if "[x]" not in cell.lower() and not compiled.search(cell):
                        evidence = cell.strip()
                        break
                # Fallback: use the last cell
                if not evidence and row.cells:
                    evidence = row.cells[-1].strip()
                return ChecklistMatch(complete=True, evidence=evidence)

    return ChecklistMatch(complete=False, evidence="")


def parse_sections(markdown: str) -> list[Section]:
    """Extract heading-delimited sections from Markdown.

    Args:
        markdown: Raw Markdown text.

    Returns:
        List of Section objects with level, title, and body text.
    """
    md = _create_parser()
    tokens = md.parse(markdown)
    sections: list[Section] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.type == "heading_open":
            level = int(token.tag[1])  # h1 -> 1, h2 -> 2, etc.
            title = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                title = tokens[i + 1].content.strip()

            # Advance past heading_close to find body tokens
            j = i + 1
            while j < len(tokens) and tokens[j].type != "heading_close":
                j += 1
            j += 1  # skip heading_close

            body_start_line = None
            if j < len(tokens):
                start_map = tokens[j].map
                if start_map is not None:
                    body_start_line = start_map[0]

            # Find end of section (next heading of same or higher level, or EOF)
            body_end_line = None
            k = j
            while k < len(tokens):
                if tokens[k].type == "heading_open":
                    next_level = int(tokens[k].tag[1])
                    end_map = tokens[k].map
                    if next_level <= level and end_map is not None:
                        body_end_line = end_map[0]
                        break
                k += 1

            # Extract body from source lines
            if body_start_line is not None:
                lines = markdown.split("\n")
                end = body_end_line if body_end_line is not None else len(lines)
                body = "\n".join(lines[body_start_line:end]).strip()
            else:
                body = ""

            sections.append(Section(level=level, title=title, body=body))
            i = j
        else:
            i += 1

    return sections


def find_section(markdown: str, heading: str, level: int = 2) -> str | None:
    """Find a specific section by heading text and level.

    Args:
        markdown: Raw Markdown text.
        heading: Heading text to search for (case-insensitive).
        level: Heading level to match (default: 2 for ##).

    Returns:
        Section body text, or None if not found.
    """
    sections = parse_sections(markdown)
    heading_lower = heading.lower()
    for section in sections:
        if section.level == level and section.title.lower() == heading_lower:
            return section.body
    return None
