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


def test_prose_after_a_decision_is_not_a_second_decision() -> None:
    """Wrapped rationale text under a sourced decision must not HOLD the handoff."""
    decisions = "- Use the retry\n  - Provenance: a\n\nMore about why.\n"
    assert _unsourced(decisions) == []


@pytest.mark.parametrize("decisions", ["", "\n\n", "{decision list}\n", "None\n", "N/A\n"])
def test_empty_placeholder_and_none_content_is_not_a_decision(decisions: str) -> None:
    assert _unsourced(decisions) == []


def test_a_paragraph_decision_is_reported() -> None:
    """Issue #6506 round 4: prose with no list marker skipped the check."""
    assert _unsourced("We chose X because Y.\n\nMore prose.\n") == [
        "unrecognized decision form: We chose X because Y."
    ]


def test_a_paragraph_after_a_placeholder_is_still_reported() -> None:
    decisions = "{decision list}\n\nWe chose X.\n"
    assert _unsourced(decisions) == ["unrecognized decision form: We chose X."]


TABLE = "| Decision | Rationale |\n|----------|-----------|\n"


def test_a_table_data_row_without_provenance_is_reported() -> None:
    """Issue #6506 round 4: the SESSION-STATE.md table form skipped the check."""
    assert _unsourced(TABLE + "| Use X | because |\n") == ["Use X"]


def test_each_table_data_row_is_its_own_decision() -> None:
    assert _unsourced(TABLE + "| Use X | a |\n| Use Y | b |\n") == ["Use X", "Use Y"]


def test_the_table_header_and_separator_are_not_decisions() -> None:
    assert _unsourced(TABLE) == []


def test_aligned_separator_cells_are_not_decisions() -> None:
    assert _unsourced("| A | B |\n|:---|---:|\n| Use X | why |\n") == ["Use X"]


def test_a_table_row_with_a_provenance_cell_is_accepted() -> None:
    table = "| Decision | Provenance |\n|---|---|\n| Use X | ADR-1 |\n"
    assert _unsourced(table) == []


@pytest.mark.parametrize("cell", ["", " ", "{source}"])
def test_a_blank_or_placeholder_provenance_cell_is_reported(cell: str) -> None:
    table = f"| Decision | Provenance |\n|---|---|\n| Use X |{cell}|\n"
    assert _unsourced(table) == ["Use X"]


def test_a_table_row_shorter_than_the_header_has_no_provenance() -> None:
    table = "| Decision | Why | Provenance |\n|---|---|---|\n| Use X | because |\n"
    assert _unsourced(table) == ["Use X"]


def test_a_none_table_row_needs_no_provenance() -> None:
    assert _unsourced(TABLE + "| None | n/a |\n") == []


def test_the_unfilled_session_state_table_is_reported() -> None:
    assert _unsourced(TABLE + "| _what_ | _why_ |\n") == ["_what_"]


def test_a_lone_pipe_row_without_a_separator_is_reported_as_content() -> None:
    assert _unsourced("| Use X | because |\n") == [
        "unrecognized decision form: | Use X | because |"
    ]


def test_a_table_followed_by_a_bullet_counts_both() -> None:
    decisions = TABLE + "| Use X | a |\n\n- Use Y\n  - Provenance: b\n"
    assert _unsourced(decisions) == ["Use X"]


@pytest.mark.parametrize("indent", [" ", "  ", "   "])
def test_a_numbered_item_indented_one_to_three_spaces_is_a_decision(indent: str) -> None:
    """CommonMark reads 1 to 3 leading spaces as a top-level list item."""
    assert _unsourced(f"{indent}1. Use X\n") == ["Use X"]


@pytest.mark.parametrize("indent", [" ", "  ", "   "])
def test_an_indented_numbered_item_with_provenance_is_accepted(indent: str) -> None:
    assert _unsourced(f"{indent}1. Use X\n{indent}   - Provenance: ADR-1\n") == []


def test_a_heading_indented_up_to_three_spaces_is_a_decision() -> None:
    assert _unsourced("   ### Use X\n") == ["Use X"]


def test_a_numbered_item_indented_four_spaces_is_reported_as_content() -> None:
    """Four spaces is an indented code block, not a list item, but it is not silent."""
    assert _unsourced("    1. Use X\n") == ["unrecognized decision form: 1. Use X"]


def test_a_numbered_item_nested_under_a_bullet_decision_is_not_a_decision() -> None:
    decisions = "- Use X\n  1. step one\n  2. step two\n  - Provenance: a\n"
    assert _unsourced(decisions) == []


def test_a_number_below_the_content_offset_of_a_numbered_decision_is_a_decision() -> None:
    """Under `1. ` (content offset 3), a 2-space `2. ` is a sibling, not nested."""
    decisions = "1. First\n  2. Second\n"
    assert _unsourced(decisions) == ["First", "Second"]


def test_a_wide_marker_raises_the_content_offset() -> None:
    """Under `10. ` the content offset is 4, so a 3-space item is a sibling."""
    decisions = "10. First\n   1. Sibling\n"
    assert _unsourced(decisions) == ["First", "Sibling"]


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


_PROVENANCE_TABLE = "| Decision | Provenance |\n|---|---|\n| Use A | PR #1 |\n| Use B |  |\n"


@pytest.mark.parametrize(
    "stray",
    [
        "- Provenance: unrelated note\n",
        "  - Provenance: unrelated note\n",
        "\n- Provenance: unrelated note\n",
    ],
)
def test_a_stray_provenance_bullet_does_not_source_the_last_table_row(stray: str) -> None:
    """A blank Provenance cell stays unsourced when a bullet follows the table."""
    assert _unsourced(_PROVENANCE_TABLE + stray) == ["Use B"]


def test_a_stray_provenance_bullet_after_a_sourced_table_changes_nothing() -> None:
    table = "| Decision | Provenance |\n|---|---|\n| Use A | PR #1 |\n"
    assert _unsourced(table + "- Provenance: unrelated note\n") == []


def test_a_decision_after_a_table_is_sourced_by_its_own_provenance() -> None:
    """The table guard clears once a new decision starts."""
    decisions = _PROVENANCE_TABLE + "\n- Use C\n  - Provenance: ADR-2\n"
    assert _unsourced(decisions) == ["Use B"]


def test_a_numbered_decision_after_a_table_takes_attribute_bullets() -> None:
    decisions = _PROVENANCE_TABLE + "\n1. Use C\n- Provenance: ADR-2\n"
    assert _unsourced(decisions) == ["Use B"]


@pytest.mark.parametrize("decision", ["### Use X\n", "1. Use X\n"])
def test_an_empty_table_leaves_the_decision_above_it_sourceable(decision: str) -> None:
    """An empty table replaces no decision, so a later Provenance bullet still sources it."""
    empty = "\n| Decision | Provenance |\n|---|---|\n\n"
    assert _unsourced(decision + empty + "- Provenance: ADR-1\n") == []
    assert _unsourced(decision + empty) == ["Use X"]
