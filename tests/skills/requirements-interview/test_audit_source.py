"""Anchor resolution against a source specification."""

from __future__ import annotations

import pytest
from audit_paths import FIXTURES
from audit_source import (
    AnchorError,
    Section,
    find_section,
    normalize,
    parse_sections,
    resolve_anchor,
)


@pytest.fixture
def spec() -> tuple[list[str], list[Section]]:
    lines = (FIXTURES / "contradiction_spec.md").read_text(encoding="utf-8").splitlines()
    return lines, parse_sections(lines)


def test_quote_resolves_to_its_section(spec) -> None:
    lines, sections = spec
    section, text = resolve_anchor(
        {"section": "3.1 Session count", "quote": "at most 3 active sessions"}, lines, sections
    )
    assert section.heading == "3.1 Session count"
    assert text == "at most 3 active sessions"


def test_section_resolves_by_leading_number(spec) -> None:
    _, sections = spec
    assert find_section(sections, "5.2").heading == "5.2 Concurrency"


def test_parent_section_covers_child_text(spec) -> None:
    lines, sections = spec
    section, _ = resolve_anchor(
        {"section": "3. Limits", "quote": "idle session expires"}, lines, sections
    )
    assert section.heading == "3. Limits"


def test_quote_survives_line_wrapping() -> None:
    lines = ["# Doc", "", "## A", "alpha beta", "gamma delta"]
    _, text = resolve_anchor({"section": "A", "quote": "beta  gamma"}, lines, parse_sections(lines))
    assert text == "beta gamma"


def test_line_range_resolves_inside_section(spec) -> None:
    lines, sections = spec
    section, text = resolve_anchor({"section": "3.1", "lines": [11, 11]}, lines, sections)
    assert section.heading == "3.1 Session count"
    assert "at most 3 active sessions" in text


@pytest.mark.parametrize(
    ("anchor", "message"),
    [
        ({"section": "3.1", "quote": "at most 9 active sessions"}, "not found verbatim"),
        ({"section": "5.2", "quote": "at most 3 active sessions"}, "not found verbatim"),
        ({"section": "9.9", "quote": "x"}, "not found"),
        ({"section": "3.1"}, "quote or a line range"),
        ({"quote": "x"}, "needs a section"),
        ("3.1", "needs a section"),
        ({"section": "3.1", "quote": "   "}, "quote is empty"),
        ({"section": "3.1", "lines": [1, 2]}, "outside section"),
        ({"section": "3.1", "lines": [0, 2]}, "outside the document"),
        ({"section": "3.1", "lines": [99, 120]}, "outside the document"),
        ({"section": "3.1", "lines": "10-11"}, "integers"),
        ({"section": "3.1", "lines": [True, 10]}, "integers"),
    ],
)
def test_bad_anchor_is_rejected(spec, anchor, message) -> None:
    lines, sections = spec
    with pytest.raises(AnchorError, match=message):
        resolve_anchor(anchor, lines, sections)


def test_ambiguous_section_is_rejected() -> None:
    lines = ["# A", "## Same", "x", "## Same", "y"]
    with pytest.raises(AnchorError, match="ambiguous"):
        find_section(parse_sections(lines), "Same")


def test_fenced_heading_is_not_a_section() -> None:
    lines = ["# Doc", "```", "## Fake", "```", "## Real"]
    assert [s.heading for s in parse_sections(lines)] == ["Doc", "Real"]


def test_section_ends_at_next_sibling() -> None:
    lines = ["## A", "one", "## B", "two"]
    first, second = parse_sections(lines)
    assert (first.start, first.end, second.start, second.end) == (1, 2, 3, 4)


def test_normalize_collapses_whitespace() -> None:
    assert normalize("  a \n b\t c ") == "a b c"
