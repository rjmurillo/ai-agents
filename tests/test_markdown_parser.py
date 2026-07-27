"""Tests for scripts.utils.markdown_parser module.

Validates AST-based Markdown parsing for tables, checklists, and sections.
"""

from __future__ import annotations

import pytest

from scripts.utils.markdown_parser import (
    ChecklistMatch,
    ParsedTable,
    Section,
    TableRow,
    blank_code_block_lines,
    find_checklist_item,
    find_section,
    parse_sections,
    parse_tables,
)


class TestParseTablesBasic:
    """Test basic table parsing from Markdown AST."""

    def test_single_table(self):
        md = """\
| Header1 | Header2 |
|---------|---------|
| a       | b       |
| c       | d       |
"""
        tables = parse_tables(md)
        assert len(tables) == 1
        assert tables[0].headers == ["Header1", "Header2"]
        assert len(tables[0].rows) == 2
        assert tables[0].rows[0].cells == ["a", "b"]
        assert tables[0].rows[1].cells == ["c", "d"]

    def test_empty_markdown(self):
        assert parse_tables("") == []

    def test_no_tables(self):
        assert parse_tables("# Just a heading\n\nSome text.") == []

    def test_multiple_tables(self):
        md = """\
| A | B |
|---|---|
| 1 | 2 |

Some text between tables.

| C | D |
|---|---|
| 3 | 4 |
"""
        tables = parse_tables(md)
        assert len(tables) == 2
        assert tables[0].headers == ["A", "B"]
        assert tables[1].headers == ["C", "D"]

    def test_table_with_inline_formatting(self):
        md = """\
| Step | Status |
|------|--------|
| **Bold step** | `done` |
"""
        tables = parse_tables(md)
        assert len(tables) == 1
        assert "Bold step" in tables[0].rows[0].cells[0]


class TestParseTablesEdgeCases:
    """Test edge cases that trip up regex-based parsing."""

    def test_escaped_pipe_in_cell(self):
        md = """\
| Command | Description |
|---------|-------------|
| echo \\| grep | Filter output |
"""
        tables = parse_tables(md)
        assert len(tables) == 1
        # AST parser handles escaped pipes correctly
        assert len(tables[0].rows) >= 1

    def test_table_with_empty_cells(self):
        md = """\
| A | B | C |
|---|---|---|
|   | x |   |
"""
        tables = parse_tables(md)
        assert len(tables) == 1
        row = tables[0].rows[0]
        assert len(row.cells) == 3

    def test_single_column_table(self):
        md = """\
| Item |
|------|
| one  |
| two  |
"""
        tables = parse_tables(md)
        assert len(tables) == 1
        assert tables[0].headers == ["Item"]
        assert len(tables[0].rows) == 2


class TestFindChecklistItem:
    """Test checklist item extraction from Markdown tables."""

    CHECKLIST_TABLE = """\
| Level | Step | Done | Evidence |
|-------|------|------|----------|
| MUST | activate_project | [x] | Tool output in transcript |
| MUST | initial_instructions | [x] | Instructions loaded |
| MUST | Read HANDOFF.md | [ ] | |
| SHOULD | git status | [x] | Clean working tree |
"""

    def test_finds_completed_item(self):
        result = find_checklist_item(self.CHECKLIST_TABLE, "activate_project")
        assert result.complete is True
        assert result.evidence != ""

    def test_finds_incomplete_item(self):
        result = find_checklist_item(self.CHECKLIST_TABLE, r"HANDOFF\.md")
        assert result.complete is False

    def test_pattern_not_found(self):
        result = find_checklist_item(self.CHECKLIST_TABLE, "nonexistent_pattern")
        assert result.complete is False
        assert result.evidence == ""

    def test_case_insensitive_match(self):
        result = find_checklist_item(self.CHECKLIST_TABLE, "ACTIVATE_PROJECT")
        assert result.complete is True

    def test_regex_pattern(self):
        result = find_checklist_item(
            self.CHECKLIST_TABLE, r"initial_instructions",
        )
        assert result.complete is True
        assert "loaded" in result.evidence.lower() or result.evidence != ""

    def test_no_tables_in_content(self):
        result = find_checklist_item("Just plain text.", "anything")
        assert result.complete is False
        assert result.evidence == ""

    def test_empty_content(self):
        result = find_checklist_item("", "anything")
        assert result.complete is False

    def test_session_log_pattern(self):
        md = """\
| Level | Step | Done | Evidence |
|-------|------|------|----------|
| MUST | Create session log | [x] | File exists |
"""
        result = find_checklist_item(md, r"Create.*session.*log")
        assert result.complete is True

    def test_branch_verification_pattern(self):
        md = """\
| Level | Step | Done | Evidence |
|-------|------|------|----------|
| SHOULD | verify branch | [x] | feat/842-autonomous |
"""
        result = find_checklist_item(md, r"verify.*branch")
        assert result.complete is True

    def test_multiple_tables_searches_all(self):
        md = """\
| A | B |
|---|---|
| x | y |

| Level | Step | Done | Evidence |
|-------|------|------|----------|
| MUST | activate_project | [x] | Done |
"""
        result = find_checklist_item(md, "activate_project")
        assert result.complete is True


class TestParseSections:
    """Test Markdown section extraction."""

    def test_single_section(self):
        md = """\
## Objective

Complete the implementation.
"""
        sections = parse_sections(md)
        assert len(sections) >= 1
        obj = [s for s in sections if s.title == "Objective"]
        assert len(obj) == 1
        assert "Complete the implementation" in obj[0].body

    def test_multiple_sections(self):
        md = """\
## First

Content one.

## Second

Content two.
"""
        sections = parse_sections(md)
        titles = [s.title for s in sections]
        assert "First" in titles
        assert "Second" in titles

    def test_nested_sections(self):
        md = """\
## Parent

Parent content.

### Child

Child content.

## Sibling

Sibling content.
"""
        sections = parse_sections(md)
        parent = [s for s in sections if s.title == "Parent"]
        assert len(parent) == 1
        assert parent[0].level == 2

        child = [s for s in sections if s.title == "Child"]
        assert len(child) == 1
        assert child[0].level == 3

    def test_empty_markdown(self):
        assert parse_sections("") == []

    def test_no_headings(self):
        assert parse_sections("Just text with no headings.") == []


class TestFindSection:
    """Test section lookup by heading."""

    MD = """\
## Objective

Build the feature.

## Work Log

### Task 1

Did something.

## Summary

All done.
"""

    def test_finds_section(self):
        result = find_section(self.MD, "Objective")
        assert result is not None
        assert "Build the feature" in result

    def test_case_insensitive(self):
        result = find_section(self.MD, "objective")
        assert result is not None

    def test_not_found(self):
        result = find_section(self.MD, "Nonexistent")
        assert result is None

    def test_level_mismatch(self):
        result = find_section(self.MD, "Task 1", level=2)
        assert result is None

    def test_subsection(self):
        result = find_section(self.MD, "Task 1", level=3)
        assert result is not None
        assert "Did something" in result


class TestDataclasses:
    """Test dataclass construction and immutability."""

    def test_checklist_match_frozen(self):
        m = ChecklistMatch(complete=True, evidence="test")
        with pytest.raises(AttributeError):
            m.complete = False  # type: ignore[misc]

    def test_table_row_cells(self):
        row = TableRow(cells=["a", "b", "c"])
        assert row.cells == ["a", "b", "c"]

    def test_parsed_table_defaults(self):
        table = ParsedTable()
        assert table.headers == []
        assert table.rows == []

    def test_section_fields(self):
        s = Section(level=2, title="Test", body="Content")
        assert s.level == 2
        assert s.title == "Test"
        assert s.body == "Content"


class TestBlankCodeBlockLines:
    """AST-based code stripping for the portability validator (issue #3499)."""

    def test_blanks_fenced_block_keeps_prose(self):
        text = "keep /a\n```\ndrop /b\n```\nkeep /c\n"
        out = blank_code_block_lines(text).split("\n")
        assert out[0] == "keep /a"
        assert out[1] == ""
        assert out[2] == ""
        assert out[3] == ""
        assert out[4] == "keep /c"

    def test_blanks_indented_code_block(self):
        # A 4-space indent after a blank line is an indented code block. The old
        # line scanner never stripped these; the AST does (the #3499 fix).
        text = "prose\n\n    indented /b\n"
        out = blank_code_block_lines(text)
        assert "indented /b" not in out
        assert "prose" in out

    def test_blanks_tilde_fence(self):
        text = "~~~\ndrop /b\n~~~\n"
        assert "drop /b" not in blank_code_block_lines(text)

    def test_blanks_fence_inside_blockquote(self):
        text = "> ```\n> drop /b\n> ```\n"
        assert "drop /b" not in blank_code_block_lines(text)

    def test_blanks_fence_indented_beyond_three_spaces_in_list(self):
        # A fence aligned to a doubly-nested list lands at 4-space indent, which
        # the old ``[ \t]{0,3}`` fence regex could not match. The AST resolves
        # the list-relative indent and strips it.
        text = "- outer:\n  - inner:\n    ```bash\n    drop /b\n    ```\n"
        assert "drop /b" not in blank_code_block_lines(text)

    def test_keeps_inline_code_span(self):
        # Inline spans are not block code; the caller strips those separately.
        text = "see `keep /a` here\n"
        assert "keep /a" in blank_code_block_lines(text)

    def test_keeps_html_block(self):
        # HTML blocks are not stripped, so an unquoted ``src=`` attribute path
        # stays visible to the scanner.
        text = "<img src=/keep/a>\n"
        assert "/keep/a" in blank_code_block_lines(text)

    def test_keeps_prose_after_nested_fence_example(self):
        # A stray closing fence inside a nested example must not open a phantom
        # block that swallows real prose past the list-item boundary.
        text = (
            "1. example:\n"
            "   ```markdown\n"
            "   ### H\n"
            "   ```python\n"
            "   code\n"
            "   ```\n"
            "   ```\n"
            "\n"
            "2. real prose /keep/a\n"
        )
        assert "/keep/a" in blank_code_block_lines(text)

    def test_preserves_line_count(self):
        text = "a\n```\nb\nc\n```\nd\n"
        assert len(blank_code_block_lines(text).split("\n")) == len(text.split("\n"))

    def test_unterminated_fence_blanks_to_end(self):
        text = "```\ndrop /a\ndrop /b\n"
        out = blank_code_block_lines(text)
        assert "drop /a" not in out
        assert "drop /b" not in out

    def test_empty_string_returns_empty(self):
        assert blank_code_block_lines("") == ""

    def test_no_code_is_returned_unchanged(self):
        text = "just prose /a and more\n"
        assert blank_code_block_lines(text) == text

    def test_parser_error_propagates_not_swallowed(self, monkeypatch):
        # Fail closed: a parser failure must raise, never return clean prose that
        # would let an unparseable file slip past the gate.
        import scripts.utils.markdown_parser as mp

        class _Boom:
            def parse(self, _text):
                raise ValueError("boom")

        monkeypatch.setattr(mp, "_create_parser", lambda: _Boom())
        with pytest.raises(ValueError, match="boom"):
            mp.blank_code_block_lines("anything")
