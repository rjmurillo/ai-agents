"""Tests for scripts.utils.markdown_parser module.

Validates AST-based Markdown parsing for tables, checklists, and sections.
"""

from __future__ import annotations

import pytest

from scripts.utils.markdown_parser import (
    ChecklistMatch,
    MarkdownNestingError,
    ParsedTable,
    Section,
    TableRow,
    blank_code_block_lines,
    blank_non_prose_block_lines,
    extract_lookup_references,
    find_checklist_item,
    find_section,
    parse_sections,
    parse_tables,
)


class TestExtractLookupReferences:
    """Test rendered lookup-route extraction."""

    def test_extracts_link_and_bare_table_targets(self) -> None:
        markdown = """\
| Keywords | File |
|----------|------|
| linked | [linked](quality/linked.md) |
| bare | quality/bare |
"""

        assert extract_lookup_references(markdown) == [
            "quality/linked.md",
            "quality/bare.md",
        ]

    def test_ignores_links_outside_table_file_column(self) -> None:
        markdown = """\
| [Keywords](quality-index.md) | File |
|------------------------------|------|
| [keyword](other.md) | [target](quality/target.md) |
"""

        assert extract_lookup_references(markdown) == [
            "quality/target.md"
        ]

    def test_extracts_custom_root_lookup_links(self) -> None:
        markdown = (
            "| quality routes: [one](quality/one.md), "
            "[two](quality/two.md)\n"
        )

        assert extract_lookup_references(markdown) == [
            "quality/one.md",
            "quality/two.md",
        ]

    @pytest.mark.parametrize(
        "hidden_markup",
        [
            "<!--\n| fake: [hidden](quality/hidden.md)",
            "```\n| fake: [hidden](quality/hidden.md)\n```",
            "    | fake: [hidden](quality/hidden.md)",
            "| fake: `[hidden](quality/hidden.md)`",
            r"| fake: \[hidden](quality/hidden.md)",
        ],
    )
    def test_ignores_non_rendered_links(self, hidden_markup: str) -> None:
        assert extract_lookup_references(hidden_markup) == []

    def test_even_backslashes_preserve_rendered_link(self) -> None:
        markdown = r"| live: \\[live](quality/live.md)"

        assert extract_lookup_references(markdown) == ["quality/live.md"]

    def test_comment_marker_inside_fence_does_not_hide_later_route(self) -> None:
        markdown = (
            "```\n"
            "<!--\n"
            "```\n"
            "| live: [live](quality/live.md)\n"
        )

        assert extract_lookup_references(markdown) == ["quality/live.md"]

    def test_adjacent_prose_link_is_not_a_lookup_route(self) -> None:
        markdown = (
            "| live: [live](quality/live.md)\n"
            "ordinary prose [hidden](quality/hidden.md)\n"
        )

        assert extract_lookup_references(markdown) == ["quality/live.md"]

    def test_reference_style_root_link_uses_document_definition(self) -> None:
        markdown = (
            "| live: [live][quality]\n\n"
            "[quality]: quality/live.md\n"
        )

        assert extract_lookup_references(markdown) == ["quality/live.md"]

    def test_multiline_inline_code_link_is_not_a_route(self) -> None:
        markdown = (
            "`code starts\n"
            "| fake: [hidden](quality/hidden.md)\n"
            "code ends`\n"
            "| live: [live](quality/live.md)\n"
        )

        assert extract_lookup_references(markdown) == ["quality/live.md"]

    def test_pipe_line_nested_in_list_is_not_root_route(self) -> None:
        markdown = (
            "- example\n"
            "  | fake: [hidden](quality/hidden.md)\n"
        )

        assert extract_lookup_references(markdown) == []


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

    def test_table_cell_strips_footnote_reference(self):
        md = """\
| Agent | Use For |
|-------|---------|
| orchestrator[^agent-note] | Route and synthesize |

[^agent-note]: Additional GitHub-rendered note.
"""
        tables = parse_tables(md)
        assert len(tables) == 1
        assert tables[0].rows[0].cells[0] == "orchestrator"


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


class TestBlankCodeBlockLinesInvariants:
    """Invariants that hold for ANY correct code-stripper (issue #3499).

    Every test here passes against both the pre-#3499 line scanner and the AST
    walk, so it guards against regression but is NOT evidence the AST migration
    landed. Presenting these as RED-before proof would overstate the migration;
    the AST-specific evidence lives in :class:`TestBlankCodeBlockLinesAstBehavior`.
    """

    def test_blanks_fenced_block_keeps_prose(self):
        text = "keep /a\n```\ndrop /b\n```\nkeep /c\n"
        out = blank_code_block_lines(text).split("\n")
        assert out[0] == "keep /a"
        assert out[1] == ""
        assert out[2] == ""
        assert out[3] == ""
        assert out[4] == "keep /c"

    def test_blanks_tilde_fence(self):
        text = "~~~\ndrop /b\n~~~\n"
        assert "drop /b" not in blank_code_block_lines(text)

    def test_blanks_fence_inside_blockquote(self):
        text = "> ```\n> drop /b\n> ```\n"
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


class TestBlankNonProseBlockLines:
    """`blank_non_prose_block_lines` widens `blank_code_block_lines` to also
    blank HTML blocks (issue #5209 round-4 review: `check_adr_lifecycle.py`'s
    `_status_prose` was reading a `## Status`-shaped line out of an HTML
    comment, since `blank_code_block_lines` deliberately keeps HTML content
    visible for `check_skill_md_portability.py`'s unrelated needs; also
    discussed on PR #5230, review round 2)."""

    def test_blanks_a_block_level_html_comment(self):
        # Discrimination probe: a heading hidden inside a bare HTML comment
        # block must not survive, unlike blank_code_block_lines's behavior.
        # Asserts the exact transformed text, not just "Accepted" absent: a
        # mutant that blanks only the "Accepted" line while leaving the
        # comment's own "## Status" line intact would still pass a
        # substring-only check.
        text = "<!--\n## Status\nAccepted\n-->\n\n## Status\nProposed\n"
        out = blank_non_prose_block_lines(text)
        assert out.split("\n") == ["", "", "", "", "", "## Status", "Proposed", ""]

    def test_blank_code_block_lines_does_not_strip_the_same_comment(self):
        # Control proving the two functions genuinely differ: the same input
        # that blank_non_prose_block_lines scrubs survives the older,
        # code-only function untouched. Asserts the entire output equals the
        # input, not just that "Accepted" survives: a mutant that blanks the
        # "Accepted" line while leaving the comment's own "## Status" line
        # intact would still pass a substring-only check.
        text = "<!--\n## Status\nAccepted\n-->\n"
        assert blank_code_block_lines(text) == text

    def test_still_blanks_fenced_code(self):
        text = "keep /a\n```\ndrop /b\n```\nkeep /c\n"
        out = blank_non_prose_block_lines(text).split("\n")
        assert out[0] == "keep /a"
        assert out[1] == ""
        assert out[2] == ""
        assert out[3] == ""
        assert out[4] == "keep /c"

    def test_blanks_an_inline_html_comment_sharing_a_line_with_prose(self):
        # A comment opened mid-line (not starting the line) is not a
        # standalone html_block token; CommonMark tokenizes it as html_inline
        # instead. An earlier revision of this function left such comments
        # untouched, reasoning that only a comment segmented as its own
        # block needed hiding. That reasoning missed that an html_inline
        # comment is exactly as invisible to a renderer as an html_block one,
        # so it needs the same treatment: the multi-line variant below is
        # what actually forges a hidden status, but the single-line case is
        # the minimal instance of the same gap. Copilot found this on
        # PR #5230. Asserts the exact transformed text: prose survives,
        # the comment (markers and content) is replaced with spaces so the
        # line length and every other line's content are preserved.
        text = "prose <!-- inline --> more prose\n"
        assert blank_non_prose_block_lines(text) == "prose                 more prose\n"

    def test_blank_code_block_lines_does_not_strip_an_inline_html_comment(self):
        # Control proving the two functions still genuinely differ after the
        # fix above: blank_code_block_lines is untouched by this change and
        # keeps leaving inline HTML comments visible, matching its own
        # documented contract for check_skill_md_portability.py.
        text = "prose <!-- inline --> more prose\n"
        assert blank_code_block_lines(text) == text

    def test_hides_a_multiline_inline_html_comment_status(self):
        # The real forgery vector Copilot found (PR #5230, mandatory finding):
        # an HTML comment opened on a prose line can span multiple source
        # lines while the paragraph stays open, since none of a comment's own
        # "-->" or its hidden content interrupts a CommonMark paragraph. A
        # `**Status**: Accepted` line inside such a comment is invisible on
        # any CommonMark renderer, but the OLD blank_non_prose_block_lines
        # left every paragraph line untouched, so check_adr_lifecycle.py's
        # _INLINE_STATUS_RE would still read "Accepted" off the hidden line
        # as the record's declared status. Asserts the exact transformed
        # text: the whole comment span (spanning three source lines) becomes
        # spaces, and the surrounding prose on its own lines is untouched.
        text = "prose <!--\n**Status**: Accepted\n-->\nmore prose\n"
        out = blank_non_prose_block_lines(text)
        assert out.split("\n") == [
            "prose     ",
            "                    ",
            "   ",
            "more prose",
            "",
        ]
        # A raw-text scan for the bold status label, exactly what
        # check_adr_lifecycle.py's _INLINE_STATUS_RE does, must not find the
        # hidden declaration once this function has run.
        assert "**Status**" not in out

    def test_still_shows_status_visible_alongside_a_multiline_comment(self):
        # Control proving the fix above is not simply blanking every line the
        # comment's paragraph occupies: a real, visible status declaration
        # placed AFTER the multi-line comment on its own paragraph must
        # survive, since check_adr_lifecycle.py still has to find it.
        text = "prose <!--\nhidden\n-->\n\n**Status**: Accepted\n"
        out = blank_non_prose_block_lines(text)
        assert "**Status**: Accepted" in out

    def test_a_literal_comment_marker_inside_backticks_is_not_a_comment(self):
        # Real gap in an earlier revision of this fix, found by Copilot
        # (PR #5230, round 16, marked Mandatory): that revision scanned raw
        # text for "<!--" to find comment openers, and could not tell a real
        # comment from the same three characters written literally inside a
        # backtick code span. `` `<!--` `` is CommonMark raw text (a
        # code_inline token holding the literal characters `<!--`), not a
        # comment opener; only a `<!--` the PARSER itself classifies as
        # html_inline is a real comment. The old substring scan entered
        # "in comment" state on the backtick-quoted marker anyway and
        # blanked the real "**Status**: Proposed" that followed until the
        # next "-->" anywhere in the document. Verified empirically:
        # markdown-it tokenizes `` "`<!--` **Status**: Proposed" `` as a
        # code_inline child holding "<!--", plus separate strong_open/text/
        # strong_close tokens for the status, with no html_inline token at
        # all. Asserts the whole line survives untouched.
        text = "`<!--` **Status**: Proposed\n"
        assert blank_non_prose_block_lines(text) == text

    def test_a_decoy_code_span_does_not_steal_the_real_comments_match(self):
        # Real gap in an earlier revision of this fix, found by Copilot
        # (PR #5230, round 17, marked Mandatory): the earlier revision
        # searched for a match starting from a cursor advanced only past
        # PRIOR html_inline children, so a preceding sibling of any OTHER
        # type whose own content happened to share bytes with a later real
        # comment could steal the match. `` `<!-- x -->` <!-- x --> ``
        # tokenizes as code_inline("<!-- x -->"), text(" "),
        # html_inline("<!-- x -->"): searching for the html_inline child's
        # content from the start of the paragraph, without first having
        # advanced past the code_inline child's identical text, found the
        # FIRST occurrence (inside the backticks) and masked visible code
        # while leaving the real comment, and whatever it might hide,
        # untouched. Fixed by advancing the cursor past the source-verbatim
        # child types (`html_inline`, `code_inline`) in source order;
        # a later round narrowed this from "every child" once `text`
        # children were found unsafe to use for the same purpose (see
        # test_an_entity_decoded_text_child_cannot_steal_a_later_comments_match
        # below). Asserts the exact transformed text: the visible code span
        # survives verbatim, and only the real (second) comment is masked.
        text = "`<!-- x -->` <!-- x -->\n"
        out = blank_non_prose_block_lines(text)
        assert out.startswith("`<!-- x -->` ")
        assert "<!-- x -->" not in out[len("`<!-- x -->` ") :]

    def test_an_entity_decoded_text_child_cannot_steal_a_later_comments_match(self):
        # Real gap in the round-17 fix above, found by Copilot (PR #5230,
        # round 18, marked Mandatory, CWE-20): that fix searched EVERY
        # child's content to advance the cursor, including "text" children,
        # reasoning that any decoy needed consuming in source order. That
        # reasoning assumed a child's ``.content`` is always a verbatim
        # substring of the source, which does not hold for "text" tokens:
        # markdown-it-py resolves HTML entities, so source "&amp; " becomes
        # content "& ". Searching raw source for that DECODED string can
        # match an unrelated LATER literal "& " rather than failing to
        # match at all. Verified empirically: parsing
        # "&amp; <!--\n**Status**: Accepted\n--> & tail\n" produces a
        # leading text child whose decoded content is "& " (from the
        # source's "&amp; " span) and a later, unrelated literal "& " after
        # the real comment; searching for the decoded "& " from the
        # paragraph start found that LATER literal instead of failing,
        # advancing the cursor past the real multiline comment. The
        # subsequent search for the comment's own html_inline content then
        # started too late to find it, so no range was ever recorded, and
        # "**Status**: Accepted" stayed fully visible in the output. Fixed
        # by restricting the searchable/cursor-advancing child types to
        # "html_inline" and "code_inline", neither of which is ever
        # entity-decoded; a "text" child is now skipped without consulting
        # its content at all. Asserts the status
        # is fully masked and the entity/tail text (both real prose)
        # survive as literal, undecoded source bytes elsewhere in the
        # output blanking only replaces characters with spaces.
        text = "&amp; <!--\n**Status**: Accepted\n--> & tail\n"
        out = blank_non_prose_block_lines(text)
        assert "**Status**: Accepted" not in out
        assert "&amp;" in out
        assert "& tail" in out

    def test_a_normalized_multiline_code_span_cannot_steal_a_later_comments_match(
        self,
    ):
        # Real gap in the round-18 fix above, found by Copilot (PR #5230,
        # round 19): round 18 trusted a code_inline match once its type was
        # in the searchable allowlist, reasoning CommonMark code spans only
        # ever trim boundary whitespace and so any residual difference from
        # raw source is still a proper substring at the same relative
        # offset. That reasoning misses CommonMark's OTHER code-span
        # transform: an embedded (non-boundary) line ending inside a
        # multi-line code span is converted to a single space, which is a
        # real substitution, not mere trimming. Verified empirically:
        # parsing "`<!--\nx -->` <!-- x -->\n" produces
        # code_inline("<!-- x -->") (space-joined, not newline-joined) as
        # its first child, byte-identical to the second, real
        # html_inline("<!-- x -->") child. A bare `find` for that
        # space-joined string does not match the code span's own (newline
        # -joined) raw text, so it matches the LATER real comment's raw
        # text instead, advancing the cursor past it; the subsequent
        # html_inline search then starts too late to find anything, and
        # the whole input passed through unmodified. A first fix required a
        # code_inline match to be flanked by the token's own backtick
        # markup before being trusted; a later round (see the decoy-sibling
        # test below) found that check still insufficient and replaced it
        # entirely with delimiter-based location (`_code_span_end`), which
        # never searches by content at all. Asserts the visible multi-line
        # code span survives verbatim and the real comment is masked.
        text = "`<!--\nx -->` <!-- x -->\n"
        out = blank_non_prose_block_lines(text)
        assert out.startswith("`<!--\nx -->` ")
        assert "<!-- x -->" not in out[len("`<!--\nx -->` ") :]

    def test_a_later_decoy_code_span_cannot_steal_an_earlier_spans_match(self):
        # Real gap in the round-19 fix above, found by Copilot (PR #5230,
        # round 20): round 19's backtick-anchor check proved a candidate
        # match sat inside SOME code span of the right delimiter length,
        # but not that it was the SPECIFIC code_inline child currently
        # being processed. `` `a\nb` <!-- a b --> `a b` `` tokenizes as
        # code_inline("a b") (normalized from the newline-joined "a\nb"),
        # text(" "), html_inline("<!-- a b -->"), text(" "),
        # code_inline("a b") (the second span, genuinely "a b" verbatim,
        # no newline to normalize). Searching for the FIRST code_inline
        # child's content "a b" never finds it at its own true position
        # (whose raw text is "a\nb", not "a b"), but the anchor check
        # happily accepts the backtick-flanked "a b" inside the SECOND,
        # later code span instead, advancing the cursor past the real
        # comment sitting between them and leaving it completely
        # unmasked. Verified empirically: this exact input passed through
        # `blank_non_prose_block_lines` completely unmodified before this
        # fix. Fixed by locating each code_inline child's span from its
        # delimiter structure alone (`_code_span_end`, using
        # `_find_exact_backtick_run` to find the opening and closing
        # backtick runs), never by searching for `.content`: with no
        # content string involved, no other child's content, earlier or
        # later, can be mistaken for it. Asserts both visible code spans
        # survive verbatim and the real comment in between is masked.
        text = "`a\nb` <!-- a b --> `a b`\n"
        out = blank_non_prose_block_lines(text)
        assert out.startswith("`a\nb` ")
        assert out.endswith("`a b`\n")
        assert "a b -->" not in out
        assert "<!--" not in out

    def test_preserves_line_count(self):
        text = "a\n<!--\nb\nc\n-->\nd\n"
        original = len(text.split("\n"))
        assert len(blank_non_prose_block_lines(text).split("\n")) == original

    def test_empty_string_returns_empty(self):
        assert blank_non_prose_block_lines("") == ""

    def test_parser_error_propagates_not_swallowed(self, monkeypatch):
        import scripts.utils.markdown_parser as mp

        class _Boom:
            def parse(self, _text):
                raise ValueError("boom")

        monkeypatch.setattr(mp, "_create_parser", lambda *a, **k: _Boom())
        with pytest.raises(ValueError, match="boom"):
            mp.blank_non_prose_block_lines("anything")


class TestBlankCodeBlockLinesAstBehavior:
    """Behaviors the pre-#3499 line scanner got wrong (issue #3499).

    Each case fails against the old scanner and passes against the AST walk, so
    these are the RED-before evidence that the AST migration changed behavior,
    not merely preserved it. The equivalence run adjudicated every disagreement
    in the AST's favor.
    """

    def test_blanks_indented_code_block(self):
        # A 4-space indent after a blank line is an indented code block. The old
        # line scanner never stripped these; the AST does (the #3499 fix).
        text = "prose\n\n    indented /b\n"
        out = blank_code_block_lines(text)
        assert "indented /b" not in out
        assert "prose" in out

    def test_blanks_fence_indented_beyond_three_spaces_in_list(self):
        # A fence aligned to a doubly-nested list lands at 4-space indent, which
        # the old ``[ \t]{0,3}`` fence regex could not match. The AST resolves
        # the list-relative indent and strips it.
        text = "- outer:\n  - inner:\n    ```bash\n    drop /b\n    ```\n"
        assert "drop /b" not in blank_code_block_lines(text)

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

    def test_parser_error_propagates_not_swallowed(self, monkeypatch):
        # Fail closed: a parser failure must raise, never return clean prose that
        # would let an unparseable file slip past the gate.
        import scripts.utils.markdown_parser as mp

        class _Boom:
            def parse(self, _text):
                raise ValueError("boom")

        monkeypatch.setattr(mp, "_create_parser", lambda *a, **k: _Boom())
        with pytest.raises(ValueError, match="boom"):
            mp.blank_code_block_lines("anything")


class TestNestingExhaustion:
    """The parser's ``maxNesting`` limit must fail closed, not open (issue #3499).

    markdown-it stops emitting block tokens once container nesting reaches
    ``maxNesting`` (20 for the commonmark preset) and silently drops the rest of
    the input. A fenced ``vendor-portability`` marker or example path hidden
    that deep would then survive code-stripping and read as prose, suppressing
    genuine violations. ``blank_code_block_lines`` detects the truncation with a
    bounded second parse and refuses the file instead.
    """

    @staticmethod
    def _nested_fence(depth: int) -> str:
        quote = ">" * depth + " "
        return (
            quote + "```\n"
            + quote + "<!-- vendor-portability: example -->\n"
            + quote + "```\n"
            + "Ref .agents/analysis/foo.md.\n"
        )

    def test_depth_20_fenced_marker_is_refused(self):
        # At depth 20 the fence token vanishes, so the marker would leak. Refuse.
        with pytest.raises(MarkdownNestingError):
            blank_code_block_lines(self._nested_fence(20))

    def test_wider_variant_also_refuses_at_depth_20(self):
        # blank_non_prose_block_lines shares _blank_block_lines with
        # blank_code_block_lines, so the same fail-closed nesting guard
        # applies to it too, not just to the narrower function.
        with pytest.raises(MarkdownNestingError):
            blank_non_prose_block_lines(self._nested_fence(20))

    def test_depth_19_control_is_scanned(self):
        # Depth 19 is the last level the parser fully represents: the fence is
        # tokenized and its marker line blanked, so the file is scanned normally.
        out = blank_code_block_lines(self._nested_fence(19))
        assert "vendor-portability" not in out
        assert "Ref .agents/analysis/foo.md." in out

    def test_marker_deeper_than_both_limits_is_refused(self):
        # A marker nested past the second (detection) limit still diverges the
        # block structure between the two parses, so the moved cliff cannot fail
        # open.
        with pytest.raises(MarkdownNestingError):
            blank_code_block_lines(self._nested_fence(45))

    def test_deep_inline_nesting_is_not_refused(self):
        # Inline nesting (emphasis, links) lives in a token's children and cannot
        # hide a code block, so it must NOT trigger a refusal even at depth 19.
        text = "a " + "*" * 19 + "x" + "*" * 19 + " /keep/a\n"
        assert "/keep/a" in blank_code_block_lines(text)
