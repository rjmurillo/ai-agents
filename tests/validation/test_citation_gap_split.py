"""Two citations on one table row split without bisecting a backtick span.

``citation_anchors._gap_split`` used to pair backticks inside the gap text
alone. The gap starts with the closing backtick of the first citation's span,
so pairing was off by one. The split then landed inside a span, and the second
citation's anchors became prose fragments (issue #7656, found on
FAIL-OPEN-INVENTORY.md row 123). These tests model that row's shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Imported first: it puts scripts/validation on sys.path for citation_anchors.
from scripts.validation import check_citation_freshness  # noqa: F401
from scripts.validation.citation_anchors import (
    _BACKTICK_SPAN,
    _CITATION,
    _anchor_candidates,
    _gap_split,
    _same_line_segment,
)
from tests.validation.citation_freshness_helpers import TARGET, _add_doc, _repo, _run

HOOK = "hooks/policy.py"


def _row_123_shape(first_anchor: str, second_anchors: tuple[str, str]) -> str:
    """Build a row shaped like FAIL-OPEN-INVENTORY.md row 123."""
    one, two = second_anchors
    return (
        f"| `{HOOK}:1-2` | `{first_anchor}` | findings present; a scan crash still"
        " blocks | findings still `return 0`; typed reasons are defined at"
        f" `{TARGET}:3-4`: findings print a typed `FAIL` line with `{one}`; a"
        f" crash still blocks with exit 2 and prints a typed `FAIL` line with"
        f" `{two}` (issue #1) | ADVISORY | yes | TYPED |"
    )


def _segments(line: str) -> list[tuple[str, list[str]]]:
    matches = list(_CITATION.finditer(line))
    return [
        (m.group(0), _anchor_candidates([_same_line_segment(line, matches, i)], m.group(0)))
        for i, m in enumerate(matches)
    ]


def _span_bounds(line: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _BACKTICK_SPAN.finditer(line)]


def test_row_123_shape_gives_each_citation_its_own_span_anchors() -> None:
    line = _row_123_shape("run_advisory", ("magic_token", "return 1"))

    (first, first_anchors), (second, second_anchors) = _segments(line)

    assert first == f"{HOOK}:1-2"
    assert "run_advisory" in first_anchors
    assert second == f"{TARGET}:3-4"
    assert {"magic_token", "return 1", "FAIL"} <= set(second_anchors)


def test_row_123_shape_yields_no_prose_fragment_anchors() -> None:
    """Before the fix, text between two spans read as a span."""
    line = _row_123_shape("run_advisory", ("magic_token", "return 1"))

    for _citation, anchors in _segments(line):
        for anchor in anchors:
            assert anchor == anchor.strip(), anchors
            assert "typed reasons" not in anchor, anchors
            assert "crash still blocks" not in anchor, anchors


@pytest.mark.parametrize(
    "line",
    [
        _row_123_shape("run_advisory", ("magic_token", "return 1")),
        f"| `{HOOK}:1` | `a b` `c d` `e f` | `{TARGET}:3` |",
        f"see `{HOOK}:1` then `one two three four five` then `{TARGET}:3`",
    ],
)
def test_split_point_never_lands_inside_a_line_span(line: str) -> None:
    matches = list(_CITATION.finditer(line))
    point = _gap_split(line, matches[0].end(), matches[1].start())

    assert matches[0].end() <= point <= matches[1].start()
    for start, end in _span_bounds(line):
        assert not start < point < end, (point, start, end)


def test_split_without_spans_lands_at_the_gap_midpoint() -> None:
    line = f"{HOOK}:1 plain words only here {TARGET}:3"
    matches = list(_CITATION.finditer(line))
    prev_end, next_start = matches[0].end(), matches[1].start()

    point = _gap_split(line, prev_end, next_start)

    assert prev_end <= point <= next_start
    assert abs(point - (prev_end + (next_start - prev_end) // 2)) <= len("plain")


def test_split_stays_inside_an_empty_gap() -> None:
    """Adjacent citations leave no gap; the split cannot move off it."""
    line = f"`{HOOK}:1``{TARGET}:3`"
    matches = list(_CITATION.finditer(line))

    point = _gap_split(line, matches[0].end(), matches[1].start())

    assert matches[0].end() <= point <= matches[1].start()


def _inventory_repo(tmp_path: Path, second_anchors: tuple[str, str]) -> Path:
    """Commit a one-row inventory table that cites HOOK and TARGET."""
    root = _repo(tmp_path)
    (root / HOOK).parent.mkdir(parents=True, exist_ok=True)
    (root / HOOK).write_text("def run_advisory():\n    return 0\n", encoding="utf-8")
    header = "| A | B | C | D | E | F | G |\n|---|---|---|---|---|---|---|\n"
    row = _row_123_shape("run_advisory", second_anchors)
    _add_doc(root, "docs/inventory.md", f"{header}{row}\n")
    return root


def test_gate_passes_a_row_123_shape_with_correct_anchors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _inventory_repo(tmp_path, ("magic_token", "return 1"))

    code, out = _run(root, capsys)

    assert code == 0, out
    assert "examined 2 citation(s)" in out


def test_gate_fails_a_row_123_shape_whose_second_anchors_are_wrong(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _inventory_repo(tmp_path, ("no_such_token", "still_missing"))

    code, out = _run(root, capsys)

    assert code == 1
    assert f"{TARGET}:3-4" in out
    assert "no_such_token" in out
