"""Exact prose quotations retain quotes inside CommonMark code spans."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import check_citation_freshness  # noqa: F401
from scripts.validation.citation_anchors import _anchor_candidates, _anchor_matches
from tests.validation.citation_freshness_helpers import TARGET, _add_doc, _repo, _run

PASSAGES = (
    'Use the `"` character as a delimiter',
    'Use the `--format="json"` flag for output',
    'Use the ``"`"`` characters as delimiters',
)


@pytest.mark.parametrize("passage", PASSAGES)
def test_exact_quotation_preserves_inline_code_content(passage: str) -> None:
    citation = f"{TARGET}:1"
    anchors = _anchor_candidates([f'See "{passage}" in {citation}.'], citation)

    assert passage in anchors
    assert all(_anchor_matches(anchor, passage) for anchor in anchors)


@pytest.mark.parametrize("passage", PASSAGES)
@pytest.mark.parametrize("exact", [True, False], ids=["exact", "wrong"])
def test_gate_checks_literal_quotes_inside_code_spans(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], passage: str, exact: bool
) -> None:
    root = _repo(tmp_path)
    source = passage if exact else passage.replace('"', "")
    (root / TARGET).write_text(source + "\n", encoding="utf-8")
    citation = f"{TARGET}:1"
    _add_doc(root, "docs/quote.md", f'See "{passage}" in {citation}.\n')

    code, out = _run(root, capsys)

    assert code == (0 if exact else 1), out
    assert "examined 1 citation(s)" in out
