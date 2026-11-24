"""Truth table for GFM table-row detection in the citation-freshness gate."""

from __future__ import annotations

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
