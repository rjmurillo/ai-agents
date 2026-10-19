"""Guidance text of the spec coverage verdict must match what the parser does."""

from __future__ import annotations

from scripts.ci.spec_coverage_verdict import decide


def test_deferred_item_under_level_one_acceptance_still_counts_and_hint_says_why() -> None:
    body = "# Acceptance criteria\n- [x] done\n## Deferred\n- [ ] later\n"
    v = decide(True, body)
    assert not v.passed
    assert v.unchecked == ["later"]
    assert "same or a higher level" in v.reason


def test_deferred_item_at_same_level_passes() -> None:
    body = "## Acceptance criteria\n- [x] done\n## Deferred\n- [ ] later\n"
    assert decide(True, body).passed


def test_valid_heading_without_boxes_is_not_blamed_on_earlier_near_miss() -> None:
    body = "## Notes on acceptance\nnotes\n## Acceptance criteria\n1. item\n"
    v = decide(True, body)
    assert not v.passed
    assert "Notes on acceptance" not in v.reason
    assert "no checkbox items" in v.reason


def test_near_miss_is_named_when_no_accepted_heading_exists() -> None:
    v = decide(True, "## Acceptance criteria (draft)\n- [ ] a\n")
    assert "Acceptance criteria (draft)" in v.reason
