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
