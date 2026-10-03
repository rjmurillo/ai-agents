"""Defaults, required-pass table, and base tags for eval-prompt-change.py (issue #5601)."""

from __future__ import annotations

import pytest

from tests.eval.test_eval_prompt_change_stability import _result, ev


def test_is_base_unstable_defaults_to_the_non_security_minimum() -> None:
    assert ev.is_base_unstable(_result("S", 1, 1)) is True
    assert ev.is_base_unstable(_result("S", 3, 3)) is False


@pytest.mark.parametrize(("scored", "expected"), [(1, 1), (2, 2), (3, 2), (4, 3), (5, 4), (6, 4)])
def test_required_passes_table(scored: int, expected: int) -> None:
    assert ev.required_passes(scored) == expected


def test_base_tag_names_insufficient_scoring_not_flakiness() -> None:
    assert "1 of 3 required runs scored" in ev._base_tag(_result("S", 1, 1), 3)
    assert "FLAKY" not in ev._base_tag(_result("S", 1, 1), 3)
    assert ev._base_tag(_result("S", 2, 3), 3) == " [FLAKY, base unstable]"
    assert ev._base_tag(_result("S", 3, 3), 3) == ""
    assert ev._base_tag(_result("S", 0, 3), 3) == ""
