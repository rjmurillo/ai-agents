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
# row open its block; otherwise it is prose and wraps like prose.

_NEIGHBOR_ROWS = (
    "Unrelated fact | elsewhere | `no_such_token`",
    f"Token helper | `{TARGET}:3` | -",
    "Another fact | elsewhere | `another_missing_token`",
)


def test_a_row_without_a_leading_pipe_takes_no_neighbor_anchors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = "Fact | Source | Check\n--- | --- | ---\n" + "".join(f"{r}\n" for r in _NEIGHBOR_ROWS)
    _add_doc(root, "docs/table.md", doc)

    code, out = _run(root, capsys)

    assert code == 0, out
    assert "examined 1 citation(s)" in out


def test_a_row_without_a_leading_pipe_still_fails_on_its_own_wrong_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = f"Fact | Source\n--- | ---\nToken helper | `{TARGET}:3` (`no_such_token`)\n"
    _add_doc(root, "docs/table.md", doc)

    code, _out = _run(root, capsys)

    assert code == 1


@pytest.mark.parametrize("marker", ["> ", ">", "> > "])
def test_a_blockquoted_row_takes_no_neighbor_anchors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], marker: str
) -> None:
    root = _repo(tmp_path)
    rows = ("| Fact | Source | Check |", "|---|---|---|", *(f"| {r} |" for r in _NEIGHBOR_ROWS))
    _add_doc(root, "docs/table.md", "".join(f"{marker}{r}\n" for r in rows))

    code, out = _run(root, capsys)

    assert code == 0, out


def test_a_blockquoted_row_still_fails_on_its_own_wrong_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = f"> | Fact | Source |\n> |---|---|\n> | Helper | `{TARGET}:3` (`no_such_token`) |\n"
    _add_doc(root, "docs/table.md", doc)

    code, _out = _run(root, capsys)

    assert code == 1


@pytest.mark.parametrize("prefix", ["", "> "])
def test_a_prose_line_starting_with_a_pipe_still_wraps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], prefix: str
) -> None:
    root = _repo(tmp_path)
    doc = (
        f"{prefix}The helper `no_such_token` lives in\n"
        f"{prefix}| piped prose {TARGET}:3 for callers\n"
    )
    _add_doc(root, "docs/prose.md", doc)

    code, out = _run(root, capsys)

    assert code == 1, out


def test_a_pipe_line_whose_delimiter_cell_count_differs_is_prose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """GFM needs the header and delimiter rows to have equal cell counts."""
    root = _repo(tmp_path)
    doc = (
        f"| a | b | c |\n|---|---|\nThe helper `no_such_token` lives in\n| prose {TARGET}:3 here\n"
    )
    _add_doc(root, "docs/prose.md", doc)

    code, out = _run(root, capsys)

    assert code == 1, out


def test_a_blank_line_ends_the_table_block(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = (
        "| Fact | Source |\n|---|---|\n| Row | here |\n\n"
        f"The helper `no_such_token` lives in\n| prose {TARGET}:3 here\n"
    )
    _add_doc(root, "docs/prose.md", doc)

    code, out = _run(root, capsys)

    assert code == 1, out


@pytest.mark.parametrize("interrupter", ["# Next", "- item", "1. step", "```", "---", "* * *"])
def test_a_block_start_ends_the_table_so_prose_below_still_wraps(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], interrupter: str
) -> None:
    """GFM ends a table at a heading, list item, fence, or thematic break."""
    root = _repo(tmp_path)
    doc = (
        f"| Fact | Source |\n|---|---|\n| Row | here |\n{interrupter}\n"
        f"The helper `no_such_token` lives in\n{TARGET}:3 for callers\n"
    )
    _add_doc(root, "docs/prose.md", doc)

    code, out = _run(root, capsys)

    assert code == 1, out
