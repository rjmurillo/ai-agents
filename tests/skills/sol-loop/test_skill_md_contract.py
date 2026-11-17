"""ADR-108 template contract for sol-loop; see _template_contract.py."""

from __future__ import annotations

from tests.skills._template_contract import assert_template_owned_contract


def test_skill_md_matches_its_template() -> None:
    assert_template_owned_contract("sol-loop")
