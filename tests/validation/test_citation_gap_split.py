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


def test_adjacent_citations_split_inside_their_empty_gap() -> None:
    line = f"`{HOOK}:1``{TARGET}:3`"
    matches = list(_CITATION.finditer(line))

    point = _gap_split(line, matches[0].end(), matches[1].start())

    assert matches[0].end() <= point <= matches[1].start()


def test_split_is_clamped_when_the_snap_leaves_the_gap() -> None:
    """A quote around the first citation can snap the point before the gap.

    The clamp pulls it back to the gap edge, so each segment keeps its citation.
    """
    line = '"a.py:1    `echo lorem ipsum "hello` b.py:2'
    matches = list(_CITATION.finditer(line))
    prev_end, next_start = matches[0].end(), matches[1].start()

    point = _gap_split(line, prev_end, next_start)

    assert point == prev_end
    assert "a.py:1" in _same_line_segment(line, matches, 0)
    assert "b.py:2" in _same_line_segment(line, matches, 1)


def _hook_repo(tmp_path: Path) -> Path:
    """Create the fixture repo with HOOK tracked beside TARGET."""
    root = _repo(tmp_path)
    (root / HOOK).parent.mkdir(parents=True, exist_ok=True)
    (root / HOOK).write_text("def run_advisory():\n    return 0\n", encoding="utf-8")
    return root


def _inventory_repo(tmp_path: Path, second_anchors: tuple[str, str]) -> Path:
    """Commit a one-row inventory table that cites HOOK and TARGET."""
    root = _hook_repo(tmp_path)
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


def test_a_span_exactly_filling_the_gap_stays_with_the_second_citation() -> None:
    """A token bounded by the citations is gap text, not an enclosing token."""
    line = "| a.py:1`return 0`b.py:2 |"

    (first, first_anchors), (second, second_anchors) = _segments(line)

    assert first == "a.py:1"
    assert first_anchors == []
    assert second == "b.py:2"
    assert second_anchors == ["return 0"]


def test_gate_fails_when_a_gap_filling_span_proves_the_second_citation_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    (root / "a.py").write_text("return 0\n", encoding="utf-8")
    (root / "b.py").write_text("return 0\nreturn 1\n", encoding="utf-8")
    row = "| a.py:1`return 0`b.py:2 |"
    _add_doc(root, "docs/inventory.md", f"| A |\n|---|\n{row}\n")

    code, out = _run(root, capsys)

    assert code == 1, out
    assert "b.py:2" in out
    assert "return 0" in out


def test_an_escaped_backtick_inside_a_double_quoted_anchor_is_preserved() -> None:
    line = 'b.py:2 gives the raw string "Type \\` to open"'

    assert _anchor_candidates([line], "b.py:2") == ["Type \\` to open"]


def test_gate_accepts_an_escaped_backtick_inside_a_double_quoted_anchor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    (root / "b.py").write_text('x = 0\nPROMPT = r"Type \\` to open"\n', encoding="utf-8")
    row = '| b.py:2 gives the raw string "Type \\` to open" |'
    _add_doc(root, "docs/inventory.md", f"| A |\n|---|\n{row}\n")

    code, out = _run(root, capsys)

    assert code == 0, out


# A token that wraps a citation never sets the split. A double-quoted phrase
# around both citations once pulled every gap anchor to one side, so a stale
# citation lost its only anchor and passed (PR #7667 review).


def _enclosing_quote(hook_line: int, target_line: int) -> str:
    return (
        f'"See {HOOK}:{hook_line} for `run_advisory`; then see'
        f' {TARGET}:{target_line} for `magic_token`."'
    )


@pytest.mark.parametrize(
    "line",
    [
        pytest.param(f"| {_enclosing_quote(1, 3)} |", id="markdown-cell"),
        pytest.param(f"    {_enclosing_quote(1, 3)[:-1]}.{chr(34) * 3}", id="docstring-tail"),
        pytest.param(
            f"{chr(34) * 2}{_enclosing_quote(1, 3)}{chr(34) * 2}", id="one-line-docstring"
        ),
    ],
)
def test_an_enclosing_quote_leaves_each_anchor_with_its_citation(line: str) -> None:
    (_first, first_anchors), (_second, second_anchors) = _segments(line)

    assert "run_advisory" in first_anchors
    assert "magic_token" not in first_anchors
    assert "magic_token" in second_anchors
    assert "run_advisory" not in second_anchors


@pytest.mark.parametrize(
    ("hook_line", "target_line", "expected"),
    [
        pytest.param(1, 3, 0, id="both-correct"),
        pytest.param(2, 3, 1, id="first-stale"),
        pytest.param(1, 5, 1, id="second-stale"),
    ],
)
def test_gate_judges_each_citation_inside_an_enclosing_quote(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    hook_line: int,
    target_line: int,
    expected: int,
) -> None:
    root = _hook_repo(tmp_path)
    row = f"| {_enclosing_quote(hook_line, target_line)} |"
    _add_doc(root, "docs/inventory.md", f"| A |\n|---|\n{row}\n")

    code, out = _run(root, capsys)

    assert code == expected, out


# A backslash-escaped backtick outside a code span is a literal, not a span
# delimiter. Paired as a delimiter, it shifted every later span by one, so the
# split cut the second citation's only span in half (PR #7667 review).


def _escaped_backtick_row(target_line: int) -> str:
    return f"| the literal \\` marks this | `{HOOK}:1` | `return 1` | `{TARGET}:{target_line}` |"


def test_an_escaped_backtick_does_not_shift_span_pairing() -> None:
    line = _escaped_backtick_row(4)
    matches = list(_CITATION.finditer(line))
    span_start = line.index("`return 1`")

    point = _gap_split(line, matches[0].end(), matches[1].start())

    assert point <= span_start
    (_first, first_anchors), (_second, second_anchors) = _segments(line)
    assert first_anchors == []
    assert second_anchors == ["return 1"]


@pytest.mark.parametrize(("target_line", "expected"), [(4, 0), (5, 1)])
def test_gate_judges_a_span_after_an_escaped_backtick(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], target_line: int, expected: int
) -> None:
    root = _hook_repo(tmp_path)
    _add_doc(
        root,
        "docs/inventory.md",
        f"| A | B | C | D |\n|---|---|---|---|\n{_escaped_backtick_row(target_line)}\n",
    )

    code, out = _run(root, capsys)

    assert code == expected, out


def test_a_backslash_inside_a_code_span_still_closes_it() -> None:
    """Inside a code span a backslash is literal, so the next backtick closes it."""
    line = f"`a\\` `{HOOK}:1` | `return 1` | `{TARGET}:4`"

    (_first, _a), (_second, second_anchors) = _segments(line)

    assert second_anchors == ["return 1"]
