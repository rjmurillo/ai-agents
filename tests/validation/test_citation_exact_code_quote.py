"""Exact prose quotations and code-span delimiter edge cases retain citation anchors."""

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


FLAG_QUOTED_SPANS = (
    (
        '-m "not integration"',
        "not integration",
        'pytest -m "not integration"',
    ),
    (
        '--force-with-lease="refs/heads/topic"',
        "refs/heads/topic",
        'git push --force-with-lease="refs/heads/topic"',
    ),
)


@pytest.mark.parametrize(("span", "quoted", "source_line"), FLAG_QUOTED_SPANS)
def test_flag_shaped_span_retains_quoted_argument_anchor(
    span: str, quoted: str, source_line: str
) -> None:
    cited = "example.py"
    citation = f"{cited}:2"
    anchors = _anchor_candidates([f"Selection uses `{span}`, see {citation}."], citation)

    assert quoted in anchors
    assert all(_anchor_matches(anchor, source_line) for anchor in anchors if anchor == quoted)


@pytest.mark.parametrize(("span", "quoted", "source_line"), FLAG_QUOTED_SPANS)
@pytest.mark.parametrize("exact", [True, False], ids=["exact", "wrong"])
def test_gate_checks_quoted_arguments_in_flag_shaped_spans(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    span: str,
    quoted: str,
    source_line: str,
    exact: bool,
) -> None:
    root = _repo(tmp_path)
    cited = "example.py"
    source = source_line if exact else "return 1"
    (root / cited).write_text(f"return 0\n{source}\n", encoding="utf-8")
    citation = f"{cited}:2"
    _add_doc(
        root, "docs/inventory.md", f"| A |\n|---|\n| Selection uses `{span}`, see {citation}. |\n"
    )

    code, out = _run(root, capsys)

    assert code == (0 if exact else 1), out
    assert "examined 1 citation(s)" in out


UNEQUAL_BACKTICK_SPANS = (
    "``return 0`",
    "`return 0``",
)


@pytest.mark.parametrize("span", UNEQUAL_BACKTICK_SPANS)
def test_unequal_backtick_run_retains_content_anchor(span: str) -> None:
    cited = "example.py"
    citation = f"{cited}:2"
    anchors = _anchor_candidates([f"For the literal {span} sequence, see {citation}."], citation)

    assert "return 0" in anchors


@pytest.mark.parametrize("span", UNEQUAL_BACKTICK_SPANS)
@pytest.mark.parametrize("exact", [True, False], ids=["exact", "wrong"])
def test_gate_checks_content_in_unequal_backtick_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], span: str, exact: bool
) -> None:
    root = _repo(tmp_path)
    cited = "example.py"
    source = "return 0" if exact else "return 1"
    (root / cited).write_text(f"x\n{source}\n", encoding="utf-8")
    citation = f"{cited}:2"
    row = f"| For the literal {span} sequence, see {citation}. |"
    _add_doc(root, "docs/inventory.md", f"| A |\n|---|\n{row}\n")

    code, out = _run(root, capsys)

    assert code == (0 if exact else 1), out
    assert "examined 1 citation(s)" in out
