"""Backslash pairs preserve real code spans and stale-citation findings."""

from __future__ import annotations

from pathlib import Path

import pytest

# The gate makes bare sibling imports available before parser imports.
from scripts.validation import check_citation_freshness  # noqa: F401
from scripts.validation.citation_anchors import (
    _anchor_candidates,
    _gap_split,
    _mask_escaped_backticks,
    _snap_out_of_backtick_prefix,
)
from tests.validation.citation_freshness_helpers import _add_doc, _repo, _run


@pytest.mark.parametrize("backslashes", [1, 2, 3])
def test_backtick_escape_depends_on_backslash_parity(backslashes: int) -> None:
    prefix = "\\" * backslashes
    line = f"For the literal {prefix}`return 0` sequence, see example.py:2."
    point = line.index("`")

    anchors = _anchor_candidates([line], "example.py:2")
    masked = _mask_escaped_backticks(line)

    if backslashes == 2:
        assert anchors == ["return 0"]
        assert masked == line
    else:
        assert anchors == []
        assert masked[point - 1 : point + 1] == "  "
        assert len(masked) == len(line)


@pytest.mark.parametrize("backslashes", [0, 1, 2, 3, 4])
def test_split_keeps_the_full_backtick_prefix(backslashes: int) -> None:
    text = "label " + "\\" * backslashes + "`sample text`"
    start = len("label ")
    for point in range(start, start + backslashes + 1):
        assert _snap_out_of_backtick_prefix(text, point) == start


@pytest.mark.parametrize("backslashes", [2, 3, 4])
def test_gap_split_preserves_backtick_prefix(backslashes: int) -> None:
    prefix = "\\" * backslashes
    text = "left     " + prefix + "`sample` right"
    start = text.index(prefix)
    low = start - 2
    high = start + 4

    point = _gap_split(text, low, high)

    assert low <= point <= high
    assert point == start
    assert text[point:].startswith(prefix + "`")


def test_split_leaves_a_backslash_run_without_a_backtick_alone() -> None:
    text = "label " + "\\" * 3 + " suffix"
    point = len("label ") + 1
    assert _snap_out_of_backtick_prefix(text, point) == point


@pytest.mark.parametrize("backslashes", [0, 1, 2, 3])
@pytest.mark.parametrize("cited_line", [1, 2])
def test_gate_judges_a_citation_after_backslash_runs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    backslashes: int,
    cited_line: int,
) -> None:
    root = _repo(tmp_path)
    (root / "example.py").write_text("return 0\nreturn 1\n", encoding="utf-8")
    prefix = "\\" * backslashes
    row = f"| For the literal {prefix}`return 0` sequence, see example.py:{cited_line}. |"
    _add_doc(root, "docs/inventory.md", f"| A |\n|---|\n{row}\n")

    code, out = _run(root, capsys)

    expected = 1 if cited_line == 2 and backslashes in (0, 2) else 0
    assert code == expected, out
    assert "examined 1 citation(s)" in out
    if expected:
        assert "return 0" in out
