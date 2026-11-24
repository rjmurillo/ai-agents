"""Truth table for GFM table-row detection in the citation-freshness gate."""

from __future__ import annotations

import pytest

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
    ],
)
def test_table_row_truth_table(text: str, expected: list[bool]) -> None:
    assert _rows(text) == expected
