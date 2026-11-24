"""A Markdown table cell is the unit a citation asserts about.

Table cells end in `|`, not sentence punctuation, so the wrap rule in
``citation_anchors._context_lines`` used to join neighbor rows into a row's
sentence, and the same-line segment took the whole row. A re-verify command in
another cell, or in a neighbor row, then became a required anchor and failed a
correct citation (found editing a provenance table in the PR #7531 follow-ups).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import TARGET, _add_doc, _repo, _run


def _table(*rows: str) -> str:
    return "| Fact | Source | Check |\n|------|--------|-------|\n" + "".join(
        f"{r}\n" for r in rows
    )


def test_a_correct_row_ignores_its_neighbors_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    doc = _table(
        '| Unrelated fact | elsewhere | `grep -n "unrelated phrase" other.md` |',
        f"| Token helper | `{TARGET}:3` | `sed -n '3p' {TARGET}` |",
        '| Another fact | elsewhere | `grep -n "another phrase" more.md` |',
    )
    _add_doc(root, "docs/table.md", doc)

    code, out = _run(root, capsys)

    assert code == 0, out
    assert "examined 1 citation(s)" in out


def test_a_row_whose_command_is_not_at_the_cited_line_passes_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    _add_doc(root, "docs/table.md", _table(f"| Helper | `{TARGET}:3` | `grep -n helper x.md` |"))

    code, out = _run(root, capsys)

    assert code == 0, out


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
