"""Markdown recognition tests for build/scripts/validate_agent_matrix_refs.py.

Every test here operates on a literal string and touches no filesystem. That is
the seam this file is split on: the sibling suite builds throwaway repositories
and exercises resolution, the guards, and the CLI, while this one asks a single
question about markdown.

The question is whether the scan sees what a reader sees. Both failure
directions are defects and both have been found in review:

  - A table the reader sees that the scan misses hides a phantom row and the
    run exits zero. An indented table and a table without outer pipes each did
    this.
  - A table the scan sees that the reader does not hides a false positive. A
    fenced example of the matrix format did this, failing a run on a row that
    renders as code and routes nothing.

Cases are written as rendered markdown rather than as pattern probes, so a test
fails when the behavior changes rather than when a regex is rewritten.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_agent_matrix_refs as vamr  # noqa: E402

BOLD_MATRIX = """\
## Agent Capability Matrix

| Agent | Use For | Model | Avoid When |
|-------|---------|-------|-----------|
| **analyst** | Research | sonnet | Have context |
| **implementer** | Code | sonnet | Design open |
"""

PLAIN_MATRIX = """\
### Support Agents

| Agent | File | Role |
|-------|------|------|
| skillbook | `skillbook.md` | Skill management |
| explainer | `explainer.md` | Docs |
"""

BACKTICK_MATRIX = """\
### Coded Names

| Agent | Role |
|-------|------|
| `analyst` | Research |
"""

BOLD_HEADER_MATRIX = """\
### Bold Header

| **Agent** | Role |
|-----------|------|
| **analyst** | Research |
"""


def _names(text: str) -> list[str]:
    """Return just the agent names parsed from ``text``."""
    rows, _ = vamr.parse_matrix_rows(text)
    return [name for name, _ in rows]


class TestParseMatrixRows:
    """Row extraction from markdown."""

    def test_bold_names_parse(self):
        assert _names(BOLD_MATRIX) == ["analyst", "implementer"]

    def test_plain_names_parse(self):
        assert _names(PLAIN_MATRIX) == ["skillbook", "explainer"]

    def test_backtick_wrapped_names_parse(self):
        """A code-formatted name is still a routing target, not a comment.

        Leaving it unparsed is how a phantom row hid from the first version of
        this validator: the file produced other rows, so no gap was visible.
        """
        rows, unparsed = vamr.parse_matrix_rows(BACKTICK_MATRIX)
        assert [name for name, _ in rows] == ["analyst"]
        assert unparsed == []

    def test_bold_header_is_recognized(self):
        """A bolded header must not drop the whole table out of the scan."""
        assert _names(BOLD_HEADER_MATRIX) == ["analyst"]

    def test_backtick_header_is_recognized(self):
        """Header emphasis is independent of row emphasis and needs its own test.

        Round two of adversarial review showed that deleting backtick support
        from the header pattern still passed the whole suite: every fixture
        that carried a backtick carried it in a row, never in the header cell.
        """
        text = "| `Agent` | Role |\n|-------|------|\n| **analyst** | Research |\n"
        assert _names(text) == ["analyst"]

    def test_italic_header_is_recognized(self):
        text = "| *Agent* | Role |\n|-------|------|\n| **analyst** | Research |\n"
        assert _names(text) == ["analyst"]

    @pytest.mark.parametrize("header", ["AGENT", "agent", "AgEnT"])
    def test_header_match_is_case_insensitive(self, header):
        """The header pattern carries ``re.IGNORECASE`` and nothing tested it.

        A capitalization change in one copy of a matrix must not drop that whole
        table out of the scan, which is the same silent-miss failure that an
        indented table and a bolded header each produced.
        """
        text = f"| {header} | Role |\n|---|---|\n| **analyst** | Research |\n"
        assert _names(text) == ["analyst"]

    def test_line_numbers_are_one_based(self):
        rows, _ = vamr.parse_matrix_rows(BOLD_MATRIX)
        assert rows[0][1] == 5
        assert BOLD_MATRIX.splitlines()[4].startswith("| **analyst**")

    def test_multiple_matrices_in_one_file_all_parse(self):
        assert _names(BOLD_MATRIX + "\n" + PLAIN_MATRIX) == [
            "analyst",
            "implementer",
            "skillbook",
            "explainer",
        ]

    def test_table_ends_at_first_non_pipe_line(self):
        text = BOLD_MATRIX + "\nSome prose.\n\n| notatable | x |\n"
        assert _names(text) == ["analyst", "implementer"]

    def test_rows_outside_a_matrix_are_ignored(self):
        text = "| Tool | Purpose |\n|------|---------|\n| ripgrep | search |\n"
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert rows == []
        assert unparsed == []

    def test_separator_row_is_not_treated_as_data(self):
        rows, unparsed = vamr.parse_matrix_rows(BOLD_MATRIX)
        assert len(rows) == 2
        assert unparsed == []

    def test_unparsed_data_row_is_reported_not_skipped(self):
        text = (
            "| Agent | Role |\n"
            "|-------|------|\n"
            "| **analyst** | Research |\n"
            "| TODO fill this in | Unknown |\n"
        )
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert [name for name, _ in rows] == ["analyst"]
        assert len(unparsed) == 1
        assert unparsed[0][0] == 4

    def test_dotted_and_underscored_names_parse(self):
        text = "| Agent | Role |\n|---|---|\n| pr-comment-responder.prompt | x |\n"
        assert _names(text) == ["pr-comment-responder.prompt"]

    @pytest.mark.parametrize("cell", ["|  |", "| \t |"])
    def test_blank_first_cells_do_not_yield_a_name(self, cell):
        text = f"| Agent | Role |\n|---|---|\n{cell} x |\n"
        assert _names(text) == []


class TestEmphasisDelimiters:
    """Which emphasis spellings of a name parse, and which are rejected."""

    def test_italic_names_parse(self):
        """Single-asterisk emphasis is valid GFM and names a real routing target.

        Without it the row lands in ``unparsed`` and trips the degeneracy guard,
        which is a false positive on a file that renders correctly.
        """
        text = "| Agent | Role |\n|---|---|\n| *analyst* | Research |\n"
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert [name for name, _ in rows] == ["analyst"]
        assert unparsed == []

    @pytest.mark.parametrize(
        "cell",
        ["__analyst__", "_analyst_", "***analyst***", "___analyst___", "**analyst**"],
    )
    def test_symmetric_emphasis_yields_the_bare_name(self, cell):
        """Underscore is a legal name character, so the closing delimiter matters.

        With an independent optional closing group, ``__analyst__`` parsed as an
        agent literally named ``analyst__``: the opening delimiter was consumed
        as emphasis and the closing one was swallowed by the name. A conditional
        backreference ties the two together. Triple delimiters render as bold
        italic and are included for the same reason single ones are.
        """
        text = f"| Agent | Role |\n|---|---|\n| {cell} | Research |\n"
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert [name for name, _ in rows] == ["analyst"]
        assert unparsed == []

    @pytest.mark.parametrize("cell", ["*analyst**", "**analyst*", "___analyst_"])
    def test_asymmetric_emphasis_is_reported_rather_than_guessed(self, cell):
        """Mismatched delimiters do not render as emphasis, so no name is claimed.

        The row is reported as unparsed rather than silently dropped. Dropping it
        is what would let a malformed phantom row pass unnoticed; reporting it
        trips the degeneracy guard and fails the run.
        """
        text = f"| Agent | Role |\n|---|---|\n| {cell} | Research |\n"
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert rows == []
        assert len(unparsed) == 1


class TestIndentation:
    """GFM renders a table indented up to three spaces; four is a code block."""

    @pytest.mark.parametrize("indent", ["", " ", "  ", "   "])
    def test_tables_indented_up_to_three_spaces_are_scanned(self, indent):
        """A column-zero-anchored pattern is invisible to a table a reader sees.

        Round two of adversarial review hid a phantom row in a two-space-indented
        matrix and the validator exited zero.
        """
        text = (
            f"{indent}| Agent | Role |\n"
            f"{indent}|-------|------|\n"
            f"{indent}| **analyst** | Research |\n"
        )
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert [name for name, _ in rows] == ["analyst"]
        assert unparsed == []

    def test_four_space_indent_is_a_code_block_and_is_not_scanned(self):
        text = "    | Agent | Role |\n    |-------|------|\n    | **analyst** | Research |\n"
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert rows == []
        assert unparsed == []

    def test_over_indented_line_ends_the_table_without_a_parse_gap(self):
        """The continuation and row patterns must tolerate the same indent.

        If the continuation pattern were the more permissive of the two, a
        four-space line would be pulled into the table, fail to match a row and
        fail to match a separator, and be reported as a parse gap. That is a
        false positive on a file that renders correctly, and it trips the
        degeneracy guard, which exits non-zero.
        """
        text = (
            "| Agent | Role |\n"
            "|-------|------|\n"
            "| **analyst** | Research |\n"
            "    | **memory** | Over-indented |\n"
        )
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert [name for name, _ in rows] == ["analyst"]
        assert unparsed == []

    def test_indented_table_ends_at_a_non_table_line(self):
        """Indent support must not swallow prose that follows the table."""
        text = (
            "  | Agent | Role |\n"
            "  |-------|------|\n"
            "  | **analyst** | Research |\n"
            "  Some indented prose.\n"
            "  | notatable | x |\n"
        )
        assert _names(text) == ["analyst"]


class TestOuterPipesAreOptional:
    """GFM makes the leading and trailing pipes optional; the scan must agree."""

    def test_table_without_outer_pipes_is_scanned(self):
        """A review hid a phantom row in this shape and the validator exited zero.

        GitHub renders it as a table, so a reader following the routing sees the
        row that the pipe-anchored pattern could not.
        """
        text = "Agent | Focus\n------|------\n**memory** | Phantom\n"
        assert _names(text) == ["memory"]
        assert vamr.has_matrix_header(text) is True

    def test_trailing_pipe_alone_is_scanned(self):
        text = "| Agent | Focus\n|------|------\n| **analyst** | Research\n"
        assert _names(text) == ["analyst"]

    def test_prose_containing_a_pipe_is_not_a_row(self):
        """The optional leading pipe must not reach ordinary prose.

        It cannot, because a row is only parsed inside a table an alignment row
        has already opened, and prose after the table ends it.
        """
        text = "Agent | Focus\n------|------\n**analyst** | Research\n\nuse a | b syntax\n"
        assert _names(text) == ["analyst"]


class TestAlignmentRowIsRequired:
    """A header alone does not render a table, so it must not open one."""

    def test_header_without_an_alignment_row_opens_nothing(self):
        """Otherwise a stray ``| Agent |`` line in prose starts a phantom table.

        Everything under it would be enforced as routing even though the page
        shows no table at all.
        """
        text = "| Agent | Role |\n| **memory** | Not a table |\n"
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert rows == []
        assert unparsed == []
        assert vamr.has_matrix_header(text) is False

    def test_a_row_of_colons_is_not_an_alignment_row(self):
        """The alignment row must hold real alignment cells.

        A permissive character class matched a row of stray colons, which opens
        a table the reader does not see.
        """
        text = "| Agent | Role |\n| ::: | ::: |\n| **memory** | Phantom |\n"
        assert vamr.has_matrix_header(text) is False

    @pytest.mark.parametrize(
        "separator",
        ["|---|---|", "| :--- | ---: |", "|:-:|:-:|", "---|---", "| --- | --- |"],
    )
    def test_alignment_row_spellings_all_open_the_table(self, separator):
        text = f"| Agent | Role |\n{separator}\n| **analyst** | Research |\n"
        assert _names(text) == ["analyst"]


class TestFencedCodeBlocks:
    """A fenced example of the matrix format renders as code, not as routing."""

    def test_fenced_example_matrix_is_not_enforced(self):
        """A review appended one to an agent and the run failed on its example row.

        Documenting the format must not make the documentation a routing table.
        """
        text = "# Doc\n\n```markdown\n| Agent | Role |\n|---|---|\n| **memory** | Example |\n```\n"
        rows, unparsed = vamr.parse_matrix_rows(text)
        assert rows == []
        assert unparsed == []
        assert vamr.has_matrix_header(text) is False

    def test_tilde_fences_are_honored(self):
        text = "~~~\n| Agent | Role |\n|---|---|\n| **memory** | Example |\n~~~\n"
        assert _names(text) == []

    def test_a_shorter_inner_fence_does_not_close_a_longer_one(self):
        """A closing fence must be at least as long as the one it closes.

        Nesting a three-backtick block inside a four-backtick block is how a
        markdown file shows a fenced example of a fenced example.
        """
        text = "````\n```\n| Agent | Role |\n|---|---|\n| **memory** | Example |\n```\n````\n"
        assert _names(text) == []

    def test_a_fence_with_an_info_string_does_not_close_a_block(self):
        text = "```\n| Agent | Role |\n|---|---|\n| **memory** | x |\n```markdown\n"
        assert _names(text) == []

    def test_a_table_after_a_closed_fence_is_scanned(self):
        """Fence tracking must not swallow the rest of the file."""
        text = "```\ncode\n```\n\n| Agent | Role |\n|---|---|\n| **analyst** | Research |\n"
        assert _names(text) == ["analyst"]
        assert vamr.has_matrix_header(text) is True

    def test_has_matrix_header_agrees_with_the_parser(self):
        """The two must never disagree about whether a file carries a matrix.

        Disagreement is not a harmless mismatch: a file recorded as carrying a
        matrix from which zero rows parse is reported as a parse gap, which
        fails the run on a document that renders no table at all.
        """
        cases = [
            "```\n| Agent | Role |\n|---|---|\n| **memory** | x |\n```\n",
            "| Agent | Role |\n| **memory** | x |\n",
            "| Agent | Role |\n|---|---|\n| **analyst** | x |\n",
            "Agent | Role\n---|---\n**analyst** | x\n",
            "# Nothing here\n",
        ]
        for text in cases:
            has_header = vamr.has_matrix_header(text)
            rows, _ = vamr.parse_matrix_rows(text)
            assert has_header == bool(rows), text

    def test_an_info_string_line_does_not_close_an_open_fence(self):
        """A closing fence carries no info string, so ```python stays inside.

        Treating it as a close would expose the rest of the example block to
        the parser, and an illustrative row becomes an enforced routing claim.
        """
        text = (
            "```text\n```python\n| Agent | Focus |\n|---|---|\n| **ghost** | illustrative |\n```\n"
        )
        assert _names(text) == []

    def test_a_backtick_fence_does_not_close_a_tilde_fence(self):
        """A closing fence uses the same character as the opener."""
        text = "~~~\n```\n| Agent | Focus |\n|---|---|\n| **ghost** | illustrative |\n~~~\n"
        assert _names(text) == []

    def test_a_two_backtick_span_does_not_open_a_fence(self):
        """A fence needs three delimiters; ``code`` at line start is a span.

        Treating two as a fence swallows the rest of the file, and every real
        row after it goes unenforced while the run still passes.
        """
        text = (
            "``| Agent |`` is the header shape.\n"
            "\n"
            "| Agent | Focus |\n"
            "|---|---|\n"
            "| **memory** | Recall |\n"
        )
        assert _names(text) == ["memory"]


class TestRowAndTableLineAgree:
    """The row pattern and the table-line gate must share an indent tolerance.

    ``parse_matrix_rows`` gates every candidate row on ``TABLE_LINE`` before it
    reaches ``MATRIX_ROW``, so a mismatch is invisible through the parser: the
    looser pattern is simply never consulted. It is still a latent defect. If
    the gate is ever loosened, a row indented into a code block would parse.
    """

    @pytest.mark.parametrize("indent", [0, 1, 2, 3, 4, 5, 8])
    def test_the_two_patterns_accept_the_same_indents(self, indent):
        line = " " * indent + "| **memory** | Recall |"
        assert bool(vamr.TABLE_LINE.match(line)) == bool(vamr.MATRIX_ROW.match(line))

    @pytest.mark.parametrize("indent", [4, 5, 8])
    def test_an_indented_code_block_is_neither(self, indent):
        line = " " * indent + "| **memory** | Recall |"
        assert vamr.TABLE_LINE.match(line) is None
        assert vamr.MATRIX_ROW.match(line) is None
