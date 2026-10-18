"""Every decision form in ``## Decisions Made`` needs provenance (issue #6506).

The parser counted only bullet decisions, so a numbered item or a `###` heading
skipped the provenance check. These tests call ``decisions_without_provenance``
directly: the section parser is a pure function of the handoff text.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_handoff_resume as checker


def _unsourced(decisions: str) -> list[str]:
    return checker.decisions_without_provenance(f"# Handoff\n\n## Decisions Made\n\n{decisions}\n")


@pytest.mark.parametrize(
    ("decisions", "title"),
    [
        ("- Use the retry\n", "Use the retry"),
        ("* **Skip it**: why\n", "**Skip it**: why"),
        ("+ Use the retry\n", "Use the retry"),
        ("1. Use the retry\n", "Use the retry"),
        ("2) Use the retry\n", "Use the retry"),
        ("10. **Skip it**: why\n", "**Skip it**: why"),
        ("### Use the retry\n", "Use the retry"),
        ("###### Use the retry\n\nBody text.\n", "Use the retry"),
    ],
)
def test_every_decision_form_without_provenance_is_reported(decisions: str, title: str) -> None:
    assert _unsourced(decisions) == [title]


@pytest.mark.parametrize(
    "decisions",
    [
        "- Use the retry\n  - Provenance: analyst finding\n",
        "1. Use the retry\n   - Provenance: analyst finding, issue comment 3\n",
        "2) Use the retry\n  - Provenance: analyst finding\n",
        "### Use the retry\n- Provenance: analyst finding, issue comment 3\n",
        "### Use the retry\n\n  - Provenance: analyst finding\n",
        "1. Use the retry\n- Provenance: analyst finding\n",
    ],
)
def test_every_decision_form_with_provenance_is_accepted(decisions: str) -> None:
    assert _unsourced(decisions) == []


@pytest.mark.parametrize(
    "decisions",
    [
        "### Use the retry\n- Provenance:   \n",
        "### Use the retry\n- Provenance: {source}\n",
        "1. Use the retry\n   - Provenance:\n",
    ],
)
def test_empty_or_placeholder_provenance_is_reported(decisions: str) -> None:
    assert _unsourced(decisions) == ["Use the retry"]


def test_each_numbered_decision_needs_its_own_provenance() -> None:
    decisions = "1. First\n   - Provenance: a\n2. Second\n"
    assert _unsourced(decisions) == ["Second"]


def test_a_mixed_list_reports_only_the_unsourced_forms() -> None:
    decisions = (
        "- Bullet\n  - Provenance: a\n1. Numbered\n### Heading\n- Provenance: b\n- Another bullet\n"
    )
    assert _unsourced(decisions) == ["Numbered", "Another bullet"]


def test_top_level_provenance_bullet_after_a_bullet_decision_is_its_own_decision() -> None:
    """Only block-form decisions (numbered or heading) adopt an unindented Provenance bullet."""
    assert _unsourced("- Use the retry\n- Provenance: x\n") == ["Use the retry", "Provenance: x"]


@pytest.mark.parametrize(
    "decisions",
    [
        "### Use X\n- Alternatives considered: Y\n- Provenance: ADR-1\n",
        "### Use X\n- Alternatives considered: Y\n- Provenance: ADR-1\n- Superseded by: Z\n",
        "1. Use X\n- Alternatives considered: Y\n- Provenance: ADR-1\n",
        "### Use X\n- Provenance: ADR-1\n- Alternatives considered: Y\n",
        "### Use X\n- ALTERNATIVES CONSIDERED: Y\n- provenance: ADR-1\n",
    ],
)
def test_template_sibling_fields_belong_to_the_block_decision(decisions: str) -> None:
    """Issue #6506 review: `Alternatives considered` is not a decision of its own."""
    assert _unsourced(decisions) == []


def test_sibling_fields_without_provenance_report_only_the_decision() -> None:
    decisions = "### Use X\n- Alternatives considered: Y\n- Superseded by: Z\n"
    assert _unsourced(decisions) == ["Use X"]


def test_sibling_fields_do_not_source_the_next_decision() -> None:
    decisions = "### First\n- Provenance: a\n### Second\n- Alternatives considered: b\n"
    assert _unsourced(decisions) == ["Second"]


def test_unknown_top_level_field_under_a_block_decision_is_still_a_bullet_decision() -> None:
    decisions = "### Use X\n- Provenance: a\n- Owner: Dana\n"
    assert _unsourced(decisions) == ["Owner: Dana"]


def test_sibling_fields_after_a_bullet_decision_stay_bullet_decisions() -> None:
    decisions = "- Use X\n- Alternatives considered: Y\n"
    assert _unsourced(decisions) == ["Use X", "Alternatives considered: Y"]


def test_grouping_heading_without_provenance_is_reported() -> None:
    """A heading is a decision. Exempting group headings would let an unsourced one hide."""
    decisions = "### Architecture\n- Use X\n  - Provenance: ADR-1\n"
    assert _unsourced(decisions) == ["Architecture"]


@pytest.mark.parametrize("decisions", ["- None\n", "1. None\n", "### N/A\n", "- **n/a**\n"])
def test_none_needs_no_provenance_in_any_form(decisions: str) -> None:
    assert _unsourced(decisions) == []


def test_prose_and_blank_lines_are_not_decisions() -> None:
    assert _unsourced("Some prose about the work.\n\n---\n\nMore prose.\n") == []


def test_a_missing_section_is_reported_once() -> None:
    assert checker.decisions_without_provenance("# Handoff\n") == [checker.MISSING_DECISIONS]


def test_a_deeper_section_boundary_ends_the_decisions() -> None:
    text = "## Decisions Made\n\n- A\n  - Provenance: a\n\n## Next Steps\n\n1. Not a decision\n"
    assert checker.decisions_without_provenance(text) == []


@pytest.mark.parametrize(
    "decisions",
    [
        "1. Use X\n   - Alternatives considered:\n     1. Fixed delay\n     2. No retry\n"
        "   - Provenance: ADR-1\n",
        "- Use X\n  - Alternatives considered:\n    - Fixed delay\n    - No retry\n"
        "  - Provenance: ADR-1\n",
    ],
)
def test_an_indented_alternatives_list_is_not_a_set_of_decisions(decisions: str) -> None:
    """Counting indented items would HOLD every handoff that lists two alternatives."""
    assert _unsourced(decisions) == []


def test_an_indented_item_does_not_borrow_or_lend_provenance() -> None:
    """Provenance on a nested line still sources only the decision above it."""
    decisions = "1. First\n   1. Nested step\n   - Provenance: a\n2. Second\n"
    assert _unsourced(decisions) == ["Second"]
