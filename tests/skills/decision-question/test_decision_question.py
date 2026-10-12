"""Tests for the decision-question engine.

Covers every scenario in issue #5408's required-scenarios table and the
mandated fixtures: over-limit split, delegated choice, dependent prune after
D1, terminal task, and a negative control proving the engine is load-bearing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import decision_question as dq
import pytest
from decision_briefs import make_brief, raw_decision

SCRIPT = Path(dq.__file__)


def _option(n: int, **overrides: Any) -> dq.Option:
    base: dict[str, Any] = {"id": f"o{n}", "label": f"Option {n}", "consequence": f"Cost {n}."}
    base.update(overrides)
    return dq.Option(**base)


def _decision(**overrides: Any) -> dq.Decision:
    base: dict[str, Any] = {
        "id": "D1",
        "statement": "Choose the session store.",
        "why_now": "Blocks the auth skeleton.",
        "options": [_option(1), _option(2)],
        "recommendation": "o2",
        "recommendation_reason": "Traffic is under the point where latency matters.",
    }
    base.update(overrides)
    return dq.Decision(**base)


# --- harness bound ----------------------------------------------------------


def test_bound_pins_observed_claude_code_schema() -> None:
    assert dq.MIN_PRESENTED_OPTIONS == 2
    assert dq.MAX_PRESENTED_OPTIONS == 4
    assert dq.MAX_QUESTIONS_PER_CALL == 4
    assert dq.HARNESS_LIMIT_OBSERVED is True
    assert "2.1.296" in dq.HARNESS_LIMIT_SOURCE


def test_reference_documents_the_pinned_bound() -> None:
    text = (SCRIPT.parents[1] / "references" / "decision-brief-protocol.md").read_text("utf-8")
    assert "| Questions per call | 1 to 4 (`MAX_QUESTIONS_PER_CALL`) |" in text
    assert (
        "| Options per question | 2 to 4 (`MIN_PRESENTED_OPTIONS`, `MAX_PRESENTED_OPTIONS`) |"
        in text
    )
    assert "2.1.296" in text


# --- routing gate -----------------------------------------------------------


def test_material_decision_asks() -> None:
    should_ask, reason = dq.route({"material_decision": True})
    assert should_ask is True
    assert "bounded decision brief" in reason


def test_no_material_decision_does_not_ask() -> None:
    should_ask, _ = dq.route({})
    assert should_ask is False


@pytest.mark.parametrize(
    "flag",
    [
        "task_terminal",
        "delegated",
        "policy_mandated",
        "acceptance_criteria_determined",
        "implementation_detail_authorized",
        "resolvable_by_evidence",
    ],
)
def test_skip_flag_beats_material_decision(flag: str) -> None:
    result = dq.evaluate(make_brief(raw_decision("D1"), **{flag: True}))
    assert result["status"] == "skip"
    assert result["should_ask"] is False
    assert "pages" not in result


def test_scenario_delegated_choice_emits_no_question() -> None:
    result = dq.evaluate(make_brief(raw_decision("D1"), delegated=True))
    assert result["status"] == "skip"
    assert "delegated" in result["reason"]


def test_scenario_policy_mandated_follows_policy() -> None:
    result = dq.evaluate(make_brief(raw_decision("D1"), policy_mandated=True))
    assert result["status"] == "skip"
    assert "policy" in result["reason"]


def test_scenario_low_impact_detail_agent_decides() -> None:
    result = dq.evaluate(make_brief(raw_decision("D1"), implementation_detail_authorized=True))
    assert result["status"] == "skip"


def test_scenario_terminal_task_blocks_optional_followup() -> None:
    result = dq.evaluate(make_brief(raw_decision("D1"), task_terminal=True))
    assert result["status"] == "skip"
    assert "STOP TOKEN" in result["reason"]


def test_terminal_wins_over_delegated_in_reason_order() -> None:
    _, reason = dq.route({"task_terminal": True, "delegated": True, "material_decision": True})
    assert "STOP TOKEN" in reason


# --- decision brief ---------------------------------------------------------


def test_scenario_two_authorized_paths_one_bounded_brief() -> None:
    result = dq.evaluate(make_brief(raw_decision("D1")))
    assert result["status"] == "ask"
    assert result["decision_id"] == "D1"
    assert result["pages"] == [["o1", "o2"]]
    assert result["split"] is False


def test_complete_decision_has_no_gaps() -> None:
    assert dq.is_complete(_decision())
    assert dq.missing_brief_fields(_decision()) == []


def test_scenario_question_lacking_consequences_fails_completeness() -> None:
    bare = _decision(options=[_option(1, consequence=""), _option(2, consequence="  ")])
    assert dq.missing_brief_fields(bare) == ["option[o1].consequence", "option[o2].consequence"]
    result = dq.evaluate(
        make_brief(
            raw_decision(
                "D1",
                options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                recommendation="a",
            )
        )
    )
    assert result["status"] == "incomplete"
    assert "option[a].consequence" in result["missing"]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"statement": " "}, "statement"),
        ({"why_now": ""}, "why_now"),
        ({"options": [_option(1)]}, "at_least_two_options"),
        ({"options": [_option(1), _option(2, label="option 1")]}, "options_not_distinct"),
        ({"options": [_option(1), _option(2, id=dq.HOLD_ID)]}, f"option[{dq.HOLD_ID}].reserved_id"),
        ({"recommendation": None}, "recommendation_or_explicit_none"),
        ({"recommendation": "zzz"}, "recommendation_unknown_option"),
        ({"recommendation_reason": ""}, "recommendation_reason"),
        ({"allow_hold": True}, "hold_reopen_condition"),
        ({"no_recommendation": True}, "recommendation_conflicts_with_no_recommendation"),
    ],
)
def test_each_gap_is_reported(overrides: dict[str, Any], expected: str) -> None:
    assert expected in dq.missing_brief_fields(_decision(**overrides))


def test_explicit_no_recommendation_is_complete_and_not_fabricated() -> None:
    honest = _decision(recommendation=None, recommendation_reason="", no_recommendation=True)
    assert dq.missing_brief_fields(honest) == []


# --- split chain over the bound ---------------------------------------------


def _ids(pages: list[list[dq.Option]]) -> list[list[str]]:
    return [[o.id for o in page] for page in pages]


def test_scenario_six_options_split_deterministically() -> None:
    pages = dq.plan_prompt_pages([_option(n) for n in range(1, 7)])
    assert _ids(pages) == [["o1", "o2", "o3", "_more"], ["o4", "o5", "o6"]]


def test_options_within_bound_stay_on_one_page() -> None:
    pages = dq.plan_prompt_pages([_option(n) for n in range(1, 5)])
    assert _ids(pages) == [["o1", "o2", "o3", "o4"]]


def test_seven_options_fill_the_final_page() -> None:
    pages = dq.plan_prompt_pages([_option(n) for n in range(1, 8)])
    assert _ids(pages) == [["o1", "o2", "o3", "_more"], ["o4", "o5", "o6", "o7"]]


def test_eight_options_leave_a_two_entry_final_page() -> None:
    pages = dq.plan_prompt_pages([_option(n) for n in range(1, 9)])
    assert _ids(pages) == [["o1", "o2", "o3", "_more"], ["o4", "o5", "o6", "_more"], ["o7", "o8"]]


@pytest.mark.parametrize("hold", [False, True])
@pytest.mark.parametrize("cap", [3, 4, 5, 6])
@pytest.mark.parametrize("count", range(2, 21))
def test_every_page_respects_bounds_and_loses_nothing(count: int, cap: int, hold: bool) -> None:
    options = [_option(n) for n in range(1, count + 1)]
    pages = dq.plan_prompt_pages(options, cap, hold=hold)
    for page in pages:
        assert dq.MIN_PRESENTED_OPTIONS <= len(page) <= cap
    reals = [o.id for page in pages for o in page if o.id not in dq.RESERVED_IDS]
    assert reals == [o.id for o in options]
    assert [p[-1].id == dq.HOLD_ID for p in pages] == [hold] * len(pages)
    assert [p[-1].id == dq.CONTINUATION_ID or hold for p in pages[:-1]] == [True] * (len(pages) - 1)


def test_hold_closes_every_page_and_takes_a_slot() -> None:
    pages = dq.plan_prompt_pages([_option(n) for n in range(1, 6)], hold=True)
    assert _ids(pages) == [["o1", "o2", "_more", "_hold"], ["o3", "o4", "o5", "_hold"]]


def test_cap_below_three_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        dq.plan_prompt_pages([_option(1), _option(2)], 2)


def test_evaluate_reports_split_with_custom_cap() -> None:
    brief = make_brief(raw_decision("D1", option_count=6))
    assert dq.evaluate(brief)["split"] is True
    assert dq.evaluate(brief, max_options=6)["split"] is False


# --- dependent decisions ----------------------------------------------------


def _chain() -> dict[str, Any]:
    return make_brief(
        raw_decision("D1"),
        raw_decision("D2", requires={"D1": "o1"}),
        raw_decision("D3", option_count=3),
    )


def test_scenario_d1_asked_before_d2() -> None:
    result = dq.evaluate(_chain())
    assert result["decision_id"] == "D1"
    assert result["deferred"] == ["D2"]
    assert result["pruned"] == []


def test_d2_becomes_actionable_when_d1_keeps_it_alive() -> None:
    brief = {**_chain(), "answers": {"D1": "o1"}}
    result = dq.evaluate(brief)
    assert result["decision_id"] == "D2"
    assert result["deferred"] == []


def test_d2_pruned_when_d1_answer_makes_it_moot() -> None:
    brief = {**_chain(), "answers": {"D1": "o2"}}
    result = dq.evaluate(brief)
    assert result["pruned"] == ["D2"]
    assert result["decision_id"] == "D3"


def test_ids_are_not_renumbered_after_a_prune() -> None:
    kept = dq.prune_chain(_chain_decisions(), {"D1": "o2"})
    assert [d.id for d in kept] == ["D1", "D3"]


def _chain_decisions() -> list[dq.Decision]:
    return [dq.Decision.from_dict(d) for d in _chain()["decisions"]]


def test_option_requires_filters_unreachable_options() -> None:
    gated = raw_decision("D2")
    gated["options"][1]["requires"] = {"D1": "o1"}
    brief = make_brief(raw_decision("D1"), gated)
    brief["answers"] = {"D1": "o2"}
    result = dq.evaluate(brief)
    # o2 on D2 requires D1=o1, so only one option survives: incomplete, not asked.
    assert result["decision_id"] == "D2"
    assert result["status"] == "incomplete"
    assert "at_least_two_options" in result["missing"]


def test_all_answered_is_resolved() -> None:
    brief = {**_chain(), "answers": {"D1": "o1", "D2": "o1", "D3": "o1"}}
    result = dq.evaluate(brief)
    assert result["status"] == "resolved"


# --- hold -------------------------------------------------------------------


def _holdable(decision_id: str = "D1", **extra: Any) -> dict[str, Any]:
    return raw_decision(
        decision_id,
        allow_hold=True,
        hold_reopen_condition="Reopen when p99 exceeds 25ms in staging.",
        **extra,
    )


def test_hold_offer_appears_on_the_page() -> None:
    result = dq.evaluate(make_brief(_holdable()))
    assert result["pages"] == [["o1", "o2", "_hold"]]


def test_scenario_hold_preserves_decision_and_reopen_condition() -> None:
    brief = make_brief(_holdable())
    brief["answers"] = {"D1": dq.HOLD_ID}
    result = dq.evaluate(brief)
    assert result["status"] == "held"
    assert result["held"] == [
        {"id": "D1", "reopen_condition": "Reopen when p99 exceeds 25ms in staging."}
    ]


def test_hold_defers_dependents_instead_of_pruning_them() -> None:
    brief = make_brief(_holdable(), raw_decision("D2", requires={"D1": "o1"}))
    brief["answers"] = {"D1": dq.HOLD_ID}
    result = dq.evaluate(brief)
    assert result["deferred"] == ["D2"]
    assert result["pruned"] == []
    assert result["status"] == "held"


def test_hold_does_not_stop_independent_decisions() -> None:
    brief = make_brief(_holdable(), raw_decision("D2"))
    brief["answers"] = {"D1": dq.HOLD_ID}
    result = dq.evaluate(brief)
    assert result["status"] == "ask"
    assert result["decision_id"] == "D2"
    assert result["held"][0]["id"] == "D1"


def test_hold_answer_without_a_hold_offer_is_malformed() -> None:
    brief = make_brief(raw_decision("D1"))
    brief["answers"] = {"D1": dq.HOLD_ID}
    with pytest.raises(ValueError, match="offers no Hold"):
        dq.evaluate(brief)


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({"D9": "o1"}, "unknown decision"),
        ({"D1": "nope"}, "not one of its options"),
        ({"D1": dq.CONTINUATION_ID}, "not one of its options"),
    ],
)
def test_bad_answers_are_malformed(answers: dict[str, str], message: str) -> None:
    brief = make_brief(raw_decision("D1"))
    brief["answers"] = answers
    with pytest.raises(ValueError, match=message):
        dq.evaluate(brief)


# --- weak evidence on an irreversible choice --------------------------------


def test_scenario_irreversible_weak_evidence_names_pre_ask_review() -> None:
    result = dq.evaluate(make_brief(raw_decision("D1"), irreversible=True, weak_evidence=True))
    assert result["pre_ask_review"] == ["decision-critic", "pre-mortem"]
    assert result["status"] == "ask"


@pytest.mark.parametrize("context", [{"irreversible": True}, {"weak_evidence": True}, {}])
def test_pre_ask_review_needs_both_flags(context: dict[str, bool]) -> None:
    assert "pre_ask_review" not in dq.evaluate(make_brief(raw_decision("D1"), **context))


# --- negative control -------------------------------------------------------


def test_negative_control_naive_request_is_vague_and_over_limit() -> None:
    """Without the engine, a six-option request with no context ships as one prompt."""
    naive = raw_decision("D1", option_count=6)
    naive.update({"why_now": "", "recommendation": None, "recommendation_reason": ""})
    for option in naive["options"]:
        option["consequence"] = ""
    assert len(naive["options"]) > dq.MAX_PRESENTED_OPTIONS
    result = dq.evaluate(make_brief(naive))
    assert result["status"] == "incomplete"
    assert {"why_now", "recommendation_or_explicit_none", "option[o1].consequence"} <= set(
        result["missing"]
    )


def test_negative_control_enriched_request_fits_the_bound() -> None:
    result = dq.evaluate(make_brief(raw_decision("D1", option_count=6)))
    assert result["status"] == "ask"
    assert all(len(page) <= dq.MAX_PRESENTED_OPTIONS for page in result["pages"])
