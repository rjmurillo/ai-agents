"""Tests for option-level deferral, stale recommendations, and paging."""

from __future__ import annotations

from typing import Any

import decision_question as dq
import pytest
from decision_briefs import make_brief, raw_decision


def _holdable(decision_id: str = "D1") -> dict[str, Any]:
    return raw_decision(
        decision_id,
        allow_hold=True,
        hold_reopen_condition="Reopen when p99 exceeds 25ms in staging.",
    )


def _gated_d2_before_d1() -> dict[str, Any]:
    gated = raw_decision("D2", option_count=3)
    gated["options"][2]["requires"] = {"D1": "o1"}
    return make_brief(gated, raw_decision("D1"))


def test_option_prerequisite_defers_its_decision_until_answered() -> None:
    result = dq.evaluate(_gated_d2_before_d1())
    assert result["decision_id"] == "D1"
    assert result["deferred"] == ["D2"]


def test_deferred_option_decision_runs_once_prerequisite_is_answered() -> None:
    brief = {**_gated_d2_before_d1(), "answers": {"D1": "o1"}}
    result = dq.evaluate(brief)
    assert result["decision_id"] == "D2"
    assert result["page"] == ["o1", "o2", "o3"]


def test_held_option_prerequisite_defers_the_decision() -> None:
    d1 = _holdable("D1")
    gated = raw_decision("D2", option_count=3)
    gated["options"][2]["requires"] = {"D1": "o1"}
    brief = make_brief(gated, d1)
    brief["answers"] = {"D1": dq.HOLD_ID}
    result = dq.evaluate(brief)
    assert result["status"] == "held"
    assert result["deferred"] == ["D2"]


def _stale_recommendation_brief() -> dict[str, Any]:
    d2 = raw_decision("D2", option_count=3, recommendation="o3")
    d2["options"][2]["requires"] = {"D1": "o1"}
    return make_brief(raw_decision("D1"), d2)


def test_filtered_recommendation_requests_revision_not_incomplete() -> None:
    brief = {**_stale_recommendation_brief(), "answers": {"D1": "o2"}}
    result = dq.evaluate(brief)
    assert result["status"] == "revise_recommendation"
    assert result["decision_id"] == "D2"
    assert result["stale_recommendation"] == "o3"
    assert result["remaining_options"] == ["o1", "o2"]


def test_revised_recommendation_leaves_a_usable_decision() -> None:
    brief = {**_stale_recommendation_brief(), "answers": {"D1": "o2"}}
    brief["decisions"][0 + 1]["recommendation"] = "o1"
    result = dq.evaluate(brief)
    assert result["status"] == "ask"
    assert result["page"] == ["o1", "o2"]


def test_no_recommendation_stance_is_never_stale() -> None:
    brief = {**_stale_recommendation_brief(), "answers": {"D1": "o2"}}
    d2 = brief["decisions"][1]
    d2.update(no_recommendation=True, recommendation=None)
    assert dq.evaluate(brief)["status"] == "ask"


def test_unknown_recommendation_stays_incomplete_not_stale() -> None:
    brief = make_brief(raw_decision("D1", recommendation="ghost"))
    result = dq.evaluate(brief)
    assert result["status"] == "incomplete"
    assert "recommendation_unknown_option" in result["missing"]


def test_duplicate_decision_ids_are_rejected() -> None:
    brief = make_brief(raw_decision("D1"), raw_decision("D1", statement="Other question."))
    with pytest.raises(ValueError, match="duplicate decision id: D1"):
        dq.evaluate(brief)


# --- paging a split decision --------------------------------------------------


def _six_options() -> dict[str, Any]:
    return make_brief(raw_decision("D1", option_count=6))


def test_split_decision_starts_on_page_zero() -> None:
    result = dq.evaluate(_six_options())
    assert result["page_index"] == 0
    assert result["page"] == ["o1", "o2", "o3", dq.CONTINUATION_ID]


def test_more_advances_to_the_next_page_and_keeps_the_decision_id() -> None:
    brief = {**_six_options(), "paging": {"D1": 1}}
    result = dq.evaluate(brief)
    assert result["status"] == "ask"
    assert result["decision_id"] == "D1"
    assert result["page"] == ["o4", "o5", "o6"]


def test_real_answer_after_paging_resolves_the_decision() -> None:
    brief = {**_six_options(), "paging": {"D1": 1}, "answers": {"D1": "o5"}}
    assert dq.evaluate(brief)["status"] == "resolved"


def test_paging_past_the_final_page_is_malformed() -> None:
    with pytest.raises(ValueError, match="has 2 page"):
        dq.evaluate({**_six_options(), "paging": {"D1": 2}})


@pytest.mark.parametrize(
    ("paging", "message"),
    [
        ({"D9": 1}, "unknown decision"),
        ({"D1": -1}, "non-negative integer"),
        ({"D1": "1"}, "non-negative integer"),
        ({"D1": True}, "non-negative integer"),
    ],
)
def test_bad_paging_is_malformed(paging: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        dq.evaluate({**_six_options(), "paging": paging})


def test_context_only_skip_needs_no_decision() -> None:
    result = dq.evaluate({"context": {"delegated": True}})
    assert result["status"] == "skip"
    assert result["should_ask"] is False
