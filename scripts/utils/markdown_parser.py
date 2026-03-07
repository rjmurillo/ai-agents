"""AST-based Markdown parsing utilities for session validation.

Provides structured extraction of Markdown tables and checklists using
markdown-it-py instead of fragile regex patterns. Simple patterns (SHAs,
dates, filenames) remain regex-based per the hybrid approach in issue #842.

Exit codes follow ADR-035 when used as a standalone script.
"""

from __future__ import annotations

import re
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


@dataclass
class Section:
    """A Markdown section with heading level, title, and body content."""

    level: int
    title: str
    body: str


def _create_parser() -> MarkdownIt:
    """Create a configured markdown-it parser with table support."""
    return MarkdownIt("commonmark").enable("table")


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
                cell_content = tokens[i + 1].content.strip()
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

            if j < len(tokens) and tokens[j].map is not None:
                body_start_line = tokens[j].map[0]
            else:
                body_start_line = None

            # Find end of section (next heading of same or higher level, or EOF)
            body_end_line = None
            k = j
            while k < len(tokens):
                if tokens[k].type == "heading_open":
                    next_level = int(tokens[k].tag[1])
                    if next_level <= level and tokens[k].map is not None:
                        body_end_line = tokens[k].map[0]
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
