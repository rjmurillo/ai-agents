"""Tests for REQ-037: `_eval_api_adapter` refusal/token_limit/incomplete
handling and `max_tokens` pass-through.

Split out of `test_anthropic_stop_metadata.py` (taste-lints file-size gate);
see `_anthropic_stop_metadata_test_support.py` for the shared loader and
`FakeTransport` double. Module-level functions, not classes (CQA cohesion
gate: a class adds a `def`); same-shaped cases are tabled under one
`@pytest.mark.parametrize` function each; `unittest.mock.MagicMock` replaces
a one-off nested fake where it needs only to record its call arguments
(CQA cohesion gate: a nested `def` also counts).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tests.eval._anthropic_stop_metadata_test_support import (
    FakeTransport,
    _anthropic_response,
    _eval_api_adapter,
)

# ---------------------------------------------------------------------------
# _eval_api_adapter: refusal / token_limit / incomplete are errors, never
# retried; a completed termination is a scored success.
# ---------------------------------------------------------------------------

_TERMINATION_OUTCOME_CASES = [
    pytest.param("refusal", "error", "ERR_REFUSAL", id="refusal_blocks"),
    pytest.param("token_limit", "error", "ERR_TOKEN_LIMIT", id="token_limit_blocks"),
    pytest.param("incomplete", "error", "ERR_INCOMPLETE", id="incomplete_blocks"),
    pytest.param("completed", "success", None, id="completed_is_scored"),
]


@pytest.mark.parametrize("termination, expected_outcome, category_attr", _TERMINATION_OUTCOME_CASES)
def test_adapter_termination_outcome(
    termination: str, expected_outcome: str, category_attr: str | None
) -> None:
    transport = FakeTransport(termination)
    adapter = _eval_api_adapter.AnthropicAPIAdapter(transport=transport, sleep=lambda _s: None)

    result = adapter.call_model("p", "m", "fx", "variant", 0)

    assert result.outcome == expected_outcome
    assert result.termination == termination
    assert transport.calls == 1
    if category_attr is not None:
        assert result.error_category == getattr(_eval_api_adapter, category_attr)
    else:
        assert result.raw_response == "response text"


def test_adapter_missing_termination_attribute_is_still_a_success() -> None:
    """A transport that predates REQ-037 has no `termination` attribute."""
    adapter = _eval_api_adapter.AnthropicAPIAdapter(
        transport=lambda prompt, model_id, system: "ok", sleep=lambda _s: None
    )

    result = adapter.call_model("p", "m", "fx", "variant", 0)

    assert result.outcome == "success"
    assert result.termination is None


def test_termination_resets_between_refusal_raise_and_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-037: `_AnthropicTransport.termination` never leaks a stale value
    across calls. One transport instance, three calls in sequence: a
    refusal, then a raise, then a completed success."""
    calls = {"n": 0}

    def fake_call_api(**kwargs: object) -> str:
        calls["n"] += 1
        metadata = kwargs.get("metadata")
        assert isinstance(metadata, dict)
        if calls["n"] == 1:
            metadata["termination"] = "refusal"
            return "refused"
        if calls["n"] == 2:
            raise RuntimeError("Anthropic API request timed out after 120s.")
        metadata["termination"] = "completed"
        return "done"

    monkeypatch.setattr(_eval_api_adapter, "call_api", fake_call_api)
    transport = _eval_api_adapter._AnthropicTransport("key", seed=None, max_tokens=1024)
    adapter = _eval_api_adapter.AnthropicAPIAdapter(transport=transport, sleep=lambda _s: None)

    first = adapter.call_model("p", "m", "fx", "variant", 0, max_retries=1)
    assert first.outcome == "error"
    assert first.termination == "refusal"

    second = adapter.call_model("p", "m", "fx", "variant", 1, max_retries=1)
    assert second.outcome == "error"
    # The raise happens after the reset-to-None and before metadata is
    # written, so the first call's "refusal" must not leak through.
    assert transport.termination is None

    third = adapter.call_model("p", "m", "fx", "variant", 2, max_retries=1)
    assert third.outcome == "success"
    assert third.termination == "completed"


def test_termination_error_category_parity() -> None:
    """The adapter's blocking map must cover exactly the terminations
    `_anthropic_response.NON_SCOREABLE_TERMINATIONS` names. A category added
    to one without the other silently un-blocks (or wrongly blocks) a
    termination in the adapter's retry loop."""
    assert (
        set(_eval_api_adapter._TERMINATION_ERROR_CATEGORIES)
        == _anthropic_response.NON_SCOREABLE_TERMINATIONS
    )


# ---------------------------------------------------------------------------
# max_tokens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, 1.5, "5", True, False])
def test_adapter_rejects_invalid_max_tokens(bad: object) -> None:
    with pytest.raises(ValueError, match="max_tokens must be an integer >= 1"):
        _eval_api_adapter.AnthropicAPIAdapter(max_tokens=bad)


def test_adapter_max_tokens_reaches_call_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    monkeypatch.setattr(_eval_api_adapter, "load_api_key", lambda: "key")
    fake_call_api = MagicMock(return_value="answer")
    monkeypatch.setattr(_eval_api_adapter, "call_api", fake_call_api)
    adapter = _eval_api_adapter.AnthropicAPIAdapter(max_tokens=333, sleep=lambda _s: None)

    result = adapter.call_model("prompt", "model", "fx", "variant", 0)

    assert result.outcome == "success"
    assert fake_call_api.call_args.kwargs["max_tokens"] == 333


def test_default_transport_factory_builds_anthropic_transport_with_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    monkeypatch.setattr(_eval_api_adapter, "load_api_key", lambda: "key")

    transport = _eval_api_adapter._default_transport_factory(max_tokens=333)

    assert isinstance(transport, _eval_api_adapter._AnthropicTransport)
    assert transport._max_tokens == 333
