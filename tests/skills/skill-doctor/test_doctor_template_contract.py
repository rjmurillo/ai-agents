"""Verify canonical template and generated entry points remain synchronized."""

from tests.skills._template_contract import assert_template_owned_contract


def test_skill_doctor_template_contract() -> None:
    assert_template_owned_contract("skill-doctor")
