"""Unit tests for `_capability_evidence`'s codex and copilot observers.

Deterministic cases over hand-built `CodexFrame`/`WireRequest`/`WireResponse`
values and Copilot-shaped JSONL events. No subprocess, no real CLI.
`test_capability_probes.py` covers these observers through the full
`probe_override` pipeline (capture, trust, classify);
`test_harness_capability_live_evidence.py` covers them against the real
checked-in captures. These tests pin each observer's own agreement and
fallback rules in isolation.
"""

from __future__ import annotations

from tests.eval._harness_capability_test_support import codex_frames as cf
from tests.eval._harness_capability_test_support import copilot_wire as cw
from tests.eval._harness_capability_test_support import evidence as ev

EvidenceKind = ev.EvidenceKind


def _frame(kind: str, response_id: str, model: str, effort: str | None, previous: str | None):
    response: dict[str, object] = {
        "id": response_id,
        "model": model,
        "previous_response_id": previous,
    }
    if effort is not None:
        response["reasoning"] = {"effort": effort}
    return cf.CodexFrame(
        timestamp="2026-09-24T12:00:00Z", payload={"type": kind, "response": response}
    )


def _created(response_id: str, model: str, effort: str, previous: str | None = None):
    return _frame("response.created", response_id, model, effort, previous)


def _completed(response_id: str, model: str, effort: str, previous: str | None = None):
    return _frame("response.completed", response_id, model, effort, previous)


# --- observe_codex_model / observe_codex_effort ---------------------------------


def test_observe_codex_model_agrees_across_child_spans() -> None:
    frames = [
        _created("parent", "gpt-5.6-sol", "medium"),
        _completed("parent", "gpt-5.6-sol", "medium"),
        _created("child_a", "gpt-6-luna", "high"),
        _completed("child_a", "gpt-6-luna", "high"),
        _created("child_b", "gpt-6-luna", "high"),
        _completed("child_b", "gpt-6-luna", "high"),
    ]

    observation = ev.observe_codex_model(frames, parent_value="gpt-5.6-sol")

    assert observation.observed == "gpt-6-luna"
    assert observation.evidence is EvidenceKind.BACKEND


def test_observe_codex_model_disagreement_among_children_verifies_nothing() -> None:
    """NEGATIVE CONTROL: a blended answer has no single author, same as copilot."""
    frames = [
        _created("parent", "gpt-5.6-sol", "medium"),
        _created("child_a", "gpt-6-luna", "high"),
        _created("child_b", "gpt-5.5", "high"),
    ]

    observation = ev.observe_codex_model(frames, parent_value="gpt-5.6-sol")

    assert observation.observed is None
    assert observation.evidence is EvidenceKind.NONE
    assert "disagreed" in observation.detail


def test_observe_codex_model_excludes_a_parent_wrap_up_turn_with_no_previous_id() -> None:
    """A parent's post-`wait_agent` turn can start a fresh chain with no
    `previous_response_id`; filtering by `parent_value` must still exclude
    it (see `codex-0.156.0/subagent-luna-high.trace.log`'s final parent
    turn), not just the very first root span."""
    frames = [
        _created("root", "gpt-5.6-sol", "medium"),
        _created("child", "gpt-6-luna", "high"),
        _completed("child", "gpt-6-luna", "high"),
        _created("wrap_up", "gpt-5.6-sol", "medium", previous=None),
    ]

    observation = ev.observe_codex_model(frames, parent_value="gpt-5.6-sol")

    assert observation.observed == "gpt-6-luna"


def test_observe_codex_model_with_no_parent_value_uses_the_lone_turn() -> None:
    """A single-turn, no-subagent probe (`parent_value=None`) reports its own value."""
    frames = [_created("only", "gpt-6-sol", "max"), _completed("only", "gpt-6-sol", "max")]

    observation = ev.observe_codex_model(frames, parent_value=None)

    assert observation.observed == "gpt-6-sol"
    assert observation.evidence is EvidenceKind.BACKEND


def test_observe_codex_effort_reports_ultra_as_max_not_the_literal_request() -> None:
    """`ultra` never comes back as `"ultra"`: the backend resolves it to `max`."""
    frames = [_created("only", "gpt-6-sol", "max"), _completed("only", "gpt-6-sol", "max")]

    observation = ev.observe_codex_effort(frames, parent_value=None)

    assert observation.observed == "max"


def test_observe_codex_model_with_no_frames_at_all_observes_nothing() -> None:
    observation = ev.observe_codex_model([], parent_value="gpt-5.6-sol")

    assert observation.observed is None
    assert observation.evidence is EvidenceKind.NONE


def test_observe_codex_model_requires_the_parent_value_to_be_observed() -> None:
    """NEGATIVE CONTROL (issue #5423 review finding 8): an assumed parent

    value that no frame ever confirms must not let a differing child value
    verify. Every span here differs from the claimed parent, which an
    unguarded "differs from parent" filter would read as unanimous child
    agreement.
    """
    frames = [
        _created("child_a", "gpt-6-luna", "high"),
        _completed("child_a", "gpt-6-luna", "high"),
        _created("child_b", "gpt-6-luna", "high"),
        _completed("child_b", "gpt-6-luna", "high"),
    ]

    observation = ev.observe_codex_model(frames, parent_value="gpt-5.6-sol")

    assert observation.observed is None
    assert observation.evidence is EvidenceKind.NONE
    assert "never observed" in observation.detail


def test_observe_codex_model_with_no_parent_context_says_so_in_the_detail() -> None:
    frames = [_created("only", "gpt-6-sol", "max"), _completed("only", "gpt-6-sol", "max")]

    observation = ev.observe_codex_model(frames, parent_value=None)

    assert observation.observed == "gpt-6-sol"
    assert observation.evidence is EvidenceKind.BACKEND
    assert "no parent context" in observation.detail


# --- observe_copilot_model --------------------------------------------------------


def _answer(
    *,
    content: str,
    model: str | None,
    api_call_id: str | None,
    agent_id: str | None = None,
):
    event: dict[str, object] = {
        "type": "assistant.message",
        "data": {"content": content, "model": model, "apiCallId": api_call_id},
    }
    if agent_id is not None:
        event["agentId"] = agent_id
    return event


def test_observe_copilot_model_prefers_the_wire_response_over_the_client_label() -> None:
    events = [
        _answer(content="hi", model="claude-haiku-4-5", api_call_id="msg_1"),
    ]
    responses = [
        cw.WireResponse(request_id="req_1", id="msg_1", model="claude-haiku-4-5-20251001", usage={})
    ]

    observation = ev.observe_copilot_model(events, responses)

    assert observation.observed == "claude-haiku-4-5-20251001"
    assert observation.evidence is EvidenceKind.BACKEND


def test_observe_copilot_model_prefers_a_child_turn_over_the_parent() -> None:
    events = [
        _answer(content="parent reply", model="claude-haiku-4-5", api_call_id="msg_parent"),
        _answer(
            content="CHILD",
            model="claude-sonnet-4-6",
            api_call_id="msg_child",
            agent_id="agent-1",
        ),
    ]
    responses = [
        cw.WireResponse(
            request_id="req_p", id="msg_parent", model="claude-haiku-4-5-20251001", usage={}
        ),
        cw.WireResponse(request_id="req_c", id="msg_child", model="claude-sonnet-4-6", usage={}),
    ]

    observation = ev.observe_copilot_model(events, responses)

    assert observation.observed == "claude-sonnet-4-6"


def test_observe_copilot_model_falls_back_to_client_echo_with_no_wire_match() -> None:
    """NEGATIVE CONTROL: the requested alias alone is CLIENT_ECHO, not BACKEND."""
    events = [_answer(content="hi", model="claude-haiku-4-5", api_call_id="msg_1")]

    observation = ev.observe_copilot_model(events, [])

    assert observation.observed == "claude-haiku-4-5"
    assert observation.evidence is EvidenceKind.CLIENT_ECHO


def test_observe_copilot_model_with_disagreeing_wire_matches_verifies_nothing() -> None:
    events = [
        _answer(content="a", model="claude-haiku-4-5", api_call_id="msg_1"),
        _answer(content="b", model="claude-haiku-4-5", api_call_id="msg_2"),
    ]
    responses = [
        cw.WireResponse(request_id="r1", id="msg_1", model="model-a", usage={}),
        cw.WireResponse(request_id="r2", id="msg_2", model="model-b", usage={}),
    ]

    observation = ev.observe_copilot_model(events, responses)

    assert observation.observed is None
    assert observation.evidence is EvidenceKind.NONE


def test_observe_copilot_model_with_no_answer_turns_observes_nothing() -> None:
    observation = ev.observe_copilot_model([], [])

    assert observation.observed is None
    assert observation.evidence is EvidenceKind.NONE


# --- observe_copilot_effort -------------------------------------------------------


def test_observe_copilot_effort_is_always_client_echo() -> None:
    """The Anthropic response never carries an effort field (see `_copilot_wire`)."""
    requests = [cw.WireRequest(model="claude-haiku-4-5", thinking_budget_tokens=1024)]

    observation = ev.observe_copilot_effort(requests)

    assert observation.observed == "1024"
    assert observation.evidence is EvidenceKind.CLIENT_ECHO


def test_observe_copilot_effort_with_disagreeing_budgets_observes_nothing() -> None:
    requests = [
        cw.WireRequest(model="claude-haiku-4-5", thinking_budget_tokens=1024),
        cw.WireRequest(model="claude-haiku-4-5", thinking_budget_tokens=4096),
    ]

    observation = ev.observe_copilot_effort(requests)

    assert observation.observed is None
    assert observation.evidence is EvidenceKind.NONE


def test_observe_copilot_effort_with_no_budget_observes_nothing() -> None:
    requests = [cw.WireRequest(model="claude-haiku-4-5", thinking_budget_tokens=None)]

    observation = ev.observe_copilot_effort(requests)

    assert observation.observed is None
    assert observation.evidence is EvidenceKind.NONE
