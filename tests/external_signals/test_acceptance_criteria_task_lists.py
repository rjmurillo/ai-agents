"""Task-list bullets and indented headings in acceptance_criteria (issue #6506)."""

from __future__ import annotations

import pytest

from scripts.external_signals import acceptance_criteria as ac


@pytest.mark.parametrize("bullet", ["+", "1.", "12)", "-", "*"])
def test_all_github_task_list_bullets_are_checkboxes(bullet: str) -> None:
    crits = ac.parse_criteria(f"## Acceptance\n\n{bullet} [ ] Do the thing\n")

    assert [c.text for c in crits] == ["Do the thing"]


def test_non_task_list_bullet_is_not_a_checkbox() -> None:
    assert ac.parse_criteria("## Acceptance\n\nx [ ] Not a list item\n") == []


@pytest.mark.parametrize("indent", [" ", "  ", "   "])
def test_heading_indented_up_to_three_spaces_is_recognized(indent: str) -> None:
    body = f"{indent}## Acceptance\n\n- [ ] Do the thing\n"

    assert len(ac.parse_criteria(body)) == 1


def test_heading_indented_four_spaces_is_a_code_block_not_a_heading() -> None:
    assert ac.parse_criteria("    ## Acceptance\n\n- [ ] Do the thing\n") == []


def test_indented_heading_ends_the_section() -> None:
    body = "## Acceptance\n\n- [ ] One\n  ## Notes\n- [ ] Not acceptance\n"

    assert len(ac.parse_criteria(body)) == 1


def test_acceptance_heading_count_sees_a_duplicate_indented_one_to_three_spaces() -> None:
    body = "## Acceptance\n\n- [ ] a\n\n ## Acceptance\n\n- [x] b\n"

    assert ac.acceptance_heading_count(body) == 2


def test_acceptance_heading_count_ignores_a_duplicate_indented_four_spaces() -> None:
    body = "## Acceptance\n\n- [ ] a\n\n    ## Acceptance\n\n- [x] b\n"

    assert ac.acceptance_heading_count(body) == 1
