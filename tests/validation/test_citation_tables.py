"""Truth table for GFM table-row detection in the citation-freshness gate."""

from __future__ import annotations

import time

import pytest

from scripts.validation import citation_tables
from scripts.validation.citation_tables import table_row


def _rows(text: str) -> list[bool]:
    lines = text.split("\n")
    return [table_row(lines, index) for index in range(len(lines))]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("| a | b |\n|---|---|\n| x | y |", [True, True, True], id="piped"),
        pytest.param("a | b\n--- | ---\nx | y", [True, True, True], id="pipeless"),
        pytest.param("> | a |\n> |---|\n> | x |", [True, True, True], id="blockquote"),
        pytest.param("| a |\n|---|\n| x |", [True, True, True], id="single-column"),
        pytest.param("a | b\n- | -\nx | y", [True, True, True], id="dash-delimiter"),
        pytest.param("intro\na | b\n---|---\nx | y", [False, True, True, True], id="after-para"),
        pytest.param("| a | b |\n|---|---|\n\n| x | y |", [True, True, False, False], id="blank"),
        pytest.param("| a | b |\n|---|---|\n# H\nprose", [True, True, False, False], id="heading"),
        pytest.param("| a | b |\n|---|---|\n- item\nprose", [True, True, False, False], id="list"),
        pytest.param("| a | b |\n|---|---|\n```\ncode", [True, True, False, False], id="fence"),
        pytest.param("| a | b |\n|---|---|\n***\nprose", [True, True, False, False], id="break"),
        pytest.param("| a |\n|---|\n| x |\n> | y |", [True, True, True, False], id="depth"),
        pytest.param("prose\n| piped prose", [False, False], id="pipe-prose"),
        pytest.param("| a | b | c |\n|---|---|", [False, False], id="cell-count"),
        pytest.param("a \\| b\n---", [False, False], id="escaped-pipe"),
        pytest.param("    | a |\n    |---|", [False, False], id="indented-code"),
        pytest.param("Title | x\n---", [False, False], id="setext"),
        pytest.param("# a | b\n---|---", [False, False], id="heading-header"),
        pytest.param("| a |\r\n|---|\r\n| x |", [True, True, True], id="crlf"),
        pytest.param("| a |\r\n|---|\r\n---\r\nx", [True, True, False, False], id="crlf-break"),
        pytest.param("| a |\n|---|\n<div>\nx", [True, True, False, False], id="html-div"),
        pytest.param("| a |\n|---|\n</details>\nx", [True, True, False, False], id="html-close"),
        pytest.param("| a |\n|---|\n<!-- c -->\nx", [True, True, False, False], id="html-comment"),
        pytest.param("| a |\n|---|\n<b>x</b> | y", [True, True, True], id="inline-html-row"),
        pytest.param("| a |\n|---|\n```x``` | y", [True, True, True], id="backtick-code-row"),
        pytest.param("| a |\n|---|\n~~~\nx", [True, True, False, False], id="tilde-fence"),
        pytest.param("| a |\n|---|\n-\u00a0x | y", [True, True, True], id="nbsp-not-list"),
        pytest.param("| a |\n|---|\n-x | y", [True, True, True], id="dash-without-gap-not-list"),
        pytest.param("| a |\n|---|\n1.x | y", [True, True, True], id="number-without-gap-not-list"),
        pytest.param("Name\n|---|\n| x |", [True, True, True], id="one-cell-unpiped-header"),
        pytest.param("Name\n:---:\nx", [True, True, True], id="one-cell-unpiped-aligned"),
        pytest.param("Name\n--:\nx", [True, True, True], id="one-cell-right-aligned"),
        pytest.param("Name\n---\nx", [False, False, False], id="bare-dashes-setext"),
        pytest.param("a | b\n    --- | ---\nx | y", [False, False, False], id="indented-delimiter"),
        pytest.param(
            "| a |\n|---|\n| x |\n<br>\ny | z", [True, True, True, False, False], id="html7-ends"
        ),
        pytest.param("<br>\nA | B\n--- | ---\nx | y", [False] * 4, id="html7-opens-block"),
        pytest.param(
            "prose\n<br>\nA | B\n--- | ---\nx | y",
            [False, False, True, True, True],
            id="html7-no-paragraph-interrupt",
        ),
        pytest.param("```\nA | B\n--- | ---\nx | y\n```", [False] * 5, id="in-fence"),
        pytest.param(
            "~~~\n```\nA | B\n--- | ---\nx | y", [False] * 5, id="tilde-not-closed-by-tick"
        ),
        pytest.param("````\n```\nA | B\n--- | ---\nx | y", [False] * 5, id="shorter-closer"),
        pytest.param("```\n``` x\nA | B\n--- | ---\nx | y", [False] * 5, id="closer-with-info"),
        pytest.param(
            "```\ncode\n```\nA | B\n--- | ---\nx | y",
            [False, False, False, True, True, True],
            id="after-closed-fence",
        ),
        pytest.param("<!--\nA | B\n--- | ---\nx | y\n-->", [False] * 5, id="in-comment"),
        pytest.param(
            "<!-- c -->\nA | B\n--- | ---", [False, True, True], id="one-line-comment-closes"
        ),
        pytest.param("<pre>\n\nA | B\n--- | ---\nx | y\n</pre>", [False] * 6, id="pre-over-blank"),
        pytest.param(
            "<div>\n\nA | B\n--- | ---\nx | y",
            [False, False, True, True, True],
            id="div-ends-at-blank",
        ),
        pytest.param("- A | B\n  --- | ---\n  x | y", [True, True, True], id="list-first-line"),
        pytest.param(
            "- | a |\n  |---|\n  | x |\n- next | y",
            [True, True, True, False],
            id="sibling-item-ends-table",
        ),
        pytest.param(
            "- Item\n\n  | a |\n  |---|\n  | x |\nprose one\nprose two",
            [False, False, True, True, True, False, False],
            id="dedent-ends-table",
        ),
        pytest.param(
            "- a\n  - b | c\n    --- | ---\n    x | y",
            [False, True, True, True],
            id="nested-list",
        ),
        pytest.param(
            "- item\n\n  ```\n  A | B\n  --- | ---\n  ```", [False] * 6, id="fence-in-item"
        ),
        pytest.param("  | a |\n  |---|\n| x |", [True, True, True], id="indent-two"),
        pytest.param(
            "- item\n\n  ```\n  > quoted\n  ```\n\n| a |\n|---|\n| x |",
            [False] * 6 + [True] * 3,
            id="quote-line-in-list-fence-keeps-fence-open",
        ),
        pytest.param(
            "- item\n\n  <!--\n  > q\n  A | B\n  --- | ---\n  x | y\n  -->",
            [False] * 8,
            id="quote-line-in-list-comment-keeps-comment-open",
        ),
        pytest.param(
            "> ```\n> > q\n> ```\n\n| a |\n|---|\n| x |",
            [False] * 4 + [True] * 3,
            id="deeper-quote-line-in-quoted-fence",
        ),
        pytest.param(
            "- item\n\n  ```\n  code\n> | a |\n> |---|\n> | x |",
            [False] * 4 + [True] * 3,
            id="dedent-closes-list-fence-into-quoted-table",
        ),
        pytest.param(
            "- item\n\n  <!--\n  note\n> | a |\n> |---|\n> | x |",
            [False] * 4 + [True] * 3,
            id="dedent-closes-list-comment-into-quoted-table",
        ),
        pytest.param(
            "<!--\nx\n--!>\nA | B\n--- | ---\nx | y",
            [False] * 6,
            id="bang-close-does-not-end-a-comment",
        ),
        pytest.param(
            "<!--\nx\n--!>\ny\n-->\nA | B\n--- | ---\nx | y",
            [False] * 5 + [True] * 3,
            id="dash-dash-close-ends-a-comment-after-bang-close",
        ),
        pytest.param(
            "<SCRIPT>\nx\n</Script>\nA | B\n--- | ---\nx | y",
            [False] * 3 + [True] * 3,
            id="html-end-tag-matches-any-case",
        ),
    ],
)
def test_table_row_truth_table(text: str, expected: list[bool]) -> None:
    assert _rows(text) == expected


def test_one_file_is_classified_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeat calls for one file are lookups, so cost stays linear in its length."""
    calls: list[int] = []
    real = citation_tables._table_rows

    def counting(lines: list[str]) -> list[bool]:
        calls.append(len(lines))
        return real(lines)

    monkeypatch.setattr(citation_tables, "_table_rows", counting)
    lines = ["| a | b |", "|---|---|", *(f"| row {n} | x |" for n in range(5000))]
    assert all(table_row(lines, index) for index in range(len(lines)))
    assert calls == [len(lines)]
    other = ["prose", "| piped prose"]
    assert not table_row(other, 1)
    assert calls == [len(lines), 2]


@pytest.mark.parametrize("marker", ["---", "***", "___"])
def test_a_long_whitespace_run_after_a_break_marker_scans_in_linear_time(marker: str) -> None:
    """Trailing whitespace has one regex owner, so a hostile line cannot backtrack."""
    lines = ["| a |", "|---|", marker + " " * 200_000 + "x"]
    started = time.perf_counter()
    assert table_row(lines, 2)
    assert time.perf_counter() - started < 1.0


def _assert_linear(lines: list[str], index: int) -> None:
    started = time.perf_counter()
    table_row(lines, index)
    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize(
    "hostile",
    [
        pytest.param("<a" + " x" * 100_000, id="unclosed-tag-many-attributes"),
        pytest.param("<a" + ' b="c"' * 50_000, id="unclosed-tag-quoted-attributes"),
        pytest.param("<a" + " " * 200_000 + "x", id="tag-whitespace-run"),
        pytest.param("<a " + "x" * 200_000, id="tag-long-name"),
    ],
)
def test_a_hostile_html_tag_line_scans_in_linear_time(hostile: str) -> None:
    """The type 7 tag pattern owns its whitespace, so no input backtracks badly."""
    _assert_linear(["| a |", "|---|", "| x |", hostile], 3)
    _assert_linear(["", hostile], 1)


@pytest.mark.parametrize(
    "hostile",
    [
        pytest.param("- " * 100_000 + "x", id="nested-markers"),
        pytest.param("-" + " " * 200_000 + "x", id="marker-gap-run"),
        pytest.param("1." + "\t" * 100_000 + "x", id="marker-tab-run"),
    ],
)
def test_a_hostile_list_marker_line_scans_in_linear_time(hostile: str) -> None:
    """The marker cap and gap handling keep a long marker line linear."""
    _assert_linear(["| a |", "|---|", hostile], 2)


def test_many_list_items_are_classified_in_linear_time() -> None:
    lines = [f"{' ' * (2 * depth)}- item {depth}" for depth in range(1500)]
    lines += ["| a |", "|---|", "| x |"]
    _assert_linear(lines, len(lines) - 1)
