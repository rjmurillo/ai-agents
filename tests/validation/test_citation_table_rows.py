"""A Markdown table row is a complete unit for the citation-freshness gate.

Table cells end in `|`, not sentence punctuation, so the wrap rule in
``citation_anchors._context_lines`` used to join neighbor rows into a row's
sentence. A neighbor row's quoted command then became a required anchor and
failed a correct citation (found editing a provenance table in the PR #7531
follow-ups). Anchors from the row's own cells still count.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import TARGET, _add_doc, _repo, _run


def _table(*rows: str) -> str:
    return "| Fact | Source | Check |\n|------|--------|-------|\n" + "".join(
        f"{r}\n" for r in rows
    )


def test_a_row_takes_no_anchors_from_its_neighbor_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = _table(
        "| Unrelated fact | elsewhere | `no_such_token` |",
        f"| Token helper | `{TARGET}:3` | - |",
        "| Another fact | elsewhere | `another_missing_token` |",
    )
    _add_doc(root, "docs/table.md", doc)

    code, out = _run(root, capsys)

    assert code == 0, out
    assert "examined 1 citation(s)" in out


def test_a_row_with_its_own_wrong_anchor_still_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = _table(f"| Token helper | `{TARGET}:3` (`no_such_token`) | `ls` |")
    _add_doc(root, "docs/table.md", doc)

    code, _out = _run(root, capsys)

    assert code == 1


def test_prose_lines_still_wrap_into_each_other(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = f"The helper `no_such_token` lives in\n{TARGET}:3 for callers\n"
    _add_doc(root, "docs/prose.md", doc)

    code, _out = _run(root, capsys)

    assert code == 1


def test_a_claim_cell_anchor_in_the_same_row_still_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A row's other cells hold the claim the citation backs, so they stay anchors."""
    root = _repo(tmp_path)
    _add_doc(root, "docs/table.md", _table(f"| `no_such_token` is honored | `{TARGET}:3` | - |"))

    code, _out = _run(root, capsys)

    assert code == 1


@pytest.mark.parametrize(("token", "expected"), [("magic_token", 0), ("no_such_token", 1)])
def test_an_anchor_only_in_the_command_cell_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], token: str, expected: int
) -> None:
    root = _repo(tmp_path)
    _add_doc(root, "docs/table.md", _table(f"| Token helper | `{TARGET}:3` | `{token}` |"))

    code, out = _run(root, capsys)

    assert code == expected, out


def test_a_row_ending_in_a_colon_takes_no_continuation_quote(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A table row is a complete unit for the continuation-quote reader too."""
    root = _repo(tmp_path)
    doc = _table(
        f"| Helper | `{TARGET}:3` | Note:",
        "  | Other | No citation | Unrelated |",
    )
    _add_doc(root, "docs/table.md", doc)

    code, out = _run(root, capsys)

    assert code == 0, out


def test_a_row_ending_in_a_colon_still_fails_on_its_own_wrong_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = _table(
        f"| Helper | `{TARGET}:3` (`no_such_token`) | Note:",
        "  | Other | No citation | Unrelated |",
    )
    _add_doc(root, "docs/table.md", doc)

    code, _out = _run(root, capsys)

    assert code == 1


# A GFM table needs no leading pipe, and it can sit inside a blockquote. A
# line that starts with `|` is a table row only when a header and delimiter
# row open its block; otherwise it is prose and wraps like prose. A blank
# line or another block start ends the table.

_NEIGHBOR_ROWS = (
    "Unrelated fact | elsewhere | `no_such_token`",
    f"Token helper | `{TARGET}:3` | -",
    "Another fact | elsewhere | `another_missing_token`",
)
_PIPED = ("| Fact | Source | Check |", "|---|---|---|", *(f"| {r} |" for r in _NEIGHBOR_ROWS))
_WRAPPED = f"The helper `no_such_token` lives in\n{TARGET}:3 for callers\n"
_TABLE_THEN = "| Fact | Source |\n|---|---|\n| Row | here |\n"


def _quoted(marker: str) -> str:
    return "".join(f"{marker}{row}\n" for row in _PIPED)


@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        pytest.param(
            "Fact | Source | Check\n--- | --- | ---\n" + "".join(f"{r}\n" for r in _NEIGHBOR_ROWS),
            0,
            id="pipeless-row-takes-no-neighbor-anchors",
        ),
        pytest.param(
            f"Fact | Source\n--- | ---\nToken helper | `{TARGET}:3` (`no_such_token`)\n",
            1,
            id="pipeless-row-own-wrong-anchor",
        ),
        *(
            pytest.param(_quoted(marker), 0, id=f"blockquoted-row[{marker}]")
            for marker in ("> ", ">", "> > ")
        ),
        pytest.param(
            f"> | Fact | Source |\n> |---|---|\n> | Helper | `{TARGET}:3` (`no_such_token`) |\n",
            1,
            id="blockquoted-row-own-wrong-anchor",
        ),
        *(
            pytest.param(
                f"{p}The helper `no_such_token` lives in\n{p}| piped prose {TARGET}:3 here\n",
                1,
                id=f"pipe-prose-wraps[{p}]",
            )
            for p in ("", "> ")
        ),
        pytest.param(
            f"| a | b | c |\n|---|---|\nThe helper `no_such_token` lives in\n| prose {TARGET}:3\n",
            1,
            id="cell-count-mismatch-is-prose",
        ),
        pytest.param(_TABLE_THEN + "\n" + _WRAPPED, 1, id="blank-line-ends-table"),
        *(
            pytest.param(
                _TABLE_THEN + f"{start}\n" + _WRAPPED, 1, id=f"block-start-ends-table[{start}]"
            )
            for start in (
                "# Next",
                "- item",
                "1. step",
                "```",
                "---",
                "* * *",
                "<div>",
                "<!-- c -->",
            )
        ),
    ],
)
def test_gfm_table_blocks_decide_which_lines_wrap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], doc: str, expected: int
) -> None:
    root = _repo(tmp_path)
    _add_doc(root, "docs/table.md", doc)

    code, out = _run(root, capsys)

    assert code == expected, out


# Table detection follows the block structure GitHub renders (cmark-gfm), not
# the line shape. Each id below is a shape where the gate's per-block read once
# disagreed with that renderer, so a correct citation failed or a stale one
# passed.
_ONE_COLUMN_ROW = f"| See `{TARGET}:3` |\n"
_NEXT_ROW = "unpiped `no_such_token`\n"


@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        pytest.param(
            "Name\n|---|\n" + _ONE_COLUMN_ROW + _NEXT_ROW,
            0,
            id="one-column-unpiped-header",
        ),
        pytest.param(
            "Name\n:---:\n" + f"See `{TARGET}:3`\n" + _NEXT_ROW,
            0,
            id="one-column-unpiped-aligned-delimiter",
        ),
        pytest.param(
            "| Name |\n:---:\n" + _ONE_COLUMN_ROW + _NEXT_ROW,
            0,
            id="one-column-piped-header-unpiped-delimiter",
        ),
        pytest.param(
            f"Name\n|---|\n| See `{TARGET}:3` (`no_such_token`) |\n",
            1,
            id="one-column-own-wrong-anchor",
        ),
        pytest.param("Name\n---\n" + _WRAPPED, 1, id="bare-dashes-stay-a-setext-heading"),
        pytest.param(
            f"Fact | Source\n    --- | ---\n{_WRAPPED}",
            1,
            id="indented-delimiter-is-a-paragraph",
        ),
        pytest.param(_TABLE_THEN + "<br>\n" + _WRAPPED, 1, id="html-standalone-tag-ends-table"),
        pytest.param(
            _TABLE_THEN + "<b>x</b> | y\n" + _WRAPPED,
            0,
            id="inline-html-line-stays-a-row",
        ),
        pytest.param(
            f"```text\nA | B\n--- | ---\n{_WRAPPED}```\n",
            1,
            id="table-shape-in-a-fence-is-prose",
        ),
        pytest.param(
            f"<div>\nA | B\n--- | ---\n{_WRAPPED}</div>\n",
            1,
            id="table-shape-in-an-html-block-is-prose",
        ),
        pytest.param(
            f"<!--\nA | B\n--- | ---\n{_WRAPPED}-->\n",
            1,
            id="table-shape-in-an-html-comment-is-prose",
        ),
        pytest.param(
            f"<pre>\n\nA | B\n--- | ---\n{_WRAPPED}</pre>\n",
            1,
            id="html-block-runs-through-a-blank-line",
        ),
        pytest.param(
            f"- A | B\n  --- | ---\n  | `{TARGET}:3` | a |\n  | `no_such_token` | b |\n",
            0,
            id="table-opens-on-a-list-item-first-line",
        ),
        pytest.param(
            f"- Item\n\n  | a |\n  |---|\n  | x |\n{_WRAPPED}",
            1,
            id="table-ends-with-its-list-item",
        ),
    ],
)
def test_block_context_decides_table_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], doc: str, expected: int
) -> None:
    root = _repo(tmp_path)
    _add_doc(root, "docs/table.md", doc)
    code, out = _run(root, capsys)
    assert code == expected, out
