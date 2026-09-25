"""Tests for REQ-037: `_eval_api_adapter` refusal/token_limit/incomplete
handling and `max_tokens` pass-through.

Split out of `test_anthropic_stop_metadata.py` (taste-lints file-size gate);
see `_anthropic_stop_metadata_test_support.py` for the shared loader.
"""

from __future__ import annotations

import pytest

from tests.eval._anthropic_stop_metadata_test_support import (
    _anthropic_response,
    _eval_api_adapter,
)

# ---------------------------------------------------------------------------
# _eval_api_adapter: refusal / token_limit / incomplete are errors, never retried
# ---------------------------------------------------------------------------


class TestTerminationErrorCategoryParity:
    def test_every_non_scoreable_termination_has_an_error_category(self) -> None:
        """The adapter's blocking map must cover exactly the terminations
        `_anthropic_response.NON_SCOREABLE_TERMINATIONS` names. A category
        added to one without the other silently un-blocks (or wrongly
        blocks) a termination in the adapter's retry loop."""
        assert (
            set(_eval_api_adapter._TERMINATION_ERROR_CATEGORIES)
            == _anthropic_response.NON_SCOREABLE_TERMINATIONS
        )


class _FakeTransport:
    """Injectable transport seam. Mirrors the shape production transports set."""

    def __init__(self, termination: str | None) -> None:
        self.calls = 0
        self.termination = termination
        self.system_fingerprint: str | None = None

    def __call__(self, prompt: str, model_id: str, system: str) -> str:
        self.calls += 1
        return "response text"


class TestAdapterTerminationHandling:
    def test_refusal_termination_is_error_and_not_retried(self) -> None:
        transport = _FakeTransport("refusal")
        adapter = _eval_api_adapter.AnthropicAPIAdapter(transport=transport, sleep=lambda _s: None)

        result = adapter.call_model("p", "m", "fx", "variant", 0)

        assert result.outcome == "error"
        assert result.error_category == _eval_api_adapter.ERR_REFUSAL
        assert result.termination == "refusal"
        assert transport.calls == 1

    def test_token_limit_termination_is_error_and_not_retried(self) -> None:
        transport = _FakeTransport("token_limit")
        adapter = _eval_api_adapter.AnthropicAPIAdapter(transport=transport, sleep=lambda _s: None)

        result = adapter.call_model("p", "m", "fx", "variant", 0)

        assert result.outcome == "error"
        assert result.error_category == _eval_api_adapter.ERR_TOKEN_LIMIT
        assert result.termination == "token_limit"
        assert transport.calls == 1

    def test_incomplete_termination_is_error_and_not_retried(self) -> None:
        transport = _FakeTransport("incomplete")
        adapter = _eval_api_adapter.AnthropicAPIAdapter(transport=transport, sleep=lambda _s: None)

        result = adapter.call_model("p", "m", "fx", "variant", 0)

        assert result.outcome == "error"
        assert result.error_category == _eval_api_adapter.ERR_INCOMPLETE
        assert result.termination == "incomplete"
        assert transport.calls == 1

    def test_completed_termination_is_a_scored_success(self) -> None:
        transport = _FakeTransport("completed")
        adapter = _eval_api_adapter.AnthropicAPIAdapter(transport=transport, sleep=lambda _s: None)

        result = adapter.call_model("p", "m", "fx", "variant", 0)

        assert result.outcome == "success"
        assert result.termination == "completed"
        assert result.raw_response == "response text"

    def test_missing_termination_attribute_is_still_a_success(self) -> None:
        """A transport that predates REQ-037 has no `termination` attribute."""

        def transport(prompt: str, model_id: str, system: str) -> str:
            return "ok"

        adapter = _eval_api_adapter.AnthropicAPIAdapter(transport=transport, sleep=lambda _s: None)

        result = adapter.call_model("p", "m", "fx", "variant", 0)

        assert result.outcome == "success"
        assert result.termination is None


class TestAnthropicTransportTerminationAcrossAttempts:
    def test_termination_resets_between_refusal_raise_and_completed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-037: `_AnthropicTransport.termination` never leaks a stale
        value across calls. One transport instance, three calls in
        sequence: a refusal, then a raise, then a completed success."""
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


class TestAdapterMaxTokens:
    def test_adapter_rejects_zero_max_tokens(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be an integer >= 1"):
            _eval_api_adapter.AnthropicAPIAdapter(max_tokens=0)

    @pytest.mark.parametrize("bad", [-1, 1.5, "5", True, False])
    def test_adapter_rejects_non_positive_int_max_tokens(self, bad: object) -> None:
        with pytest.raises(ValueError, match="max_tokens must be an integer >= 1"):
            _eval_api_adapter.AnthropicAPIAdapter(max_tokens=bad)

    def test_adapter_max_tokens_reaches_call_api(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EVAL_PROVIDER", raising=False)
        monkeypatch.setattr(_eval_api_adapter, "load_api_key", lambda: "key")
        captured: dict[str, object] = {}

        def fake_call_api(**kwargs: object) -> str:
            captured.update(kwargs)
            return "answer"

        monkeypatch.setattr(_eval_api_adapter, "call_api", fake_call_api)
        adapter = _eval_api_adapter.AnthropicAPIAdapter(max_tokens=333, sleep=lambda _s: None)

        result = adapter.call_model("prompt", "model", "fx", "variant", 0)

        assert result.outcome == "success"
        assert captured["max_tokens"] == 333

    def test_default_transport_factory_builds_anthropic_transport_with_max_tokens(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("EVAL_PROVIDER", raising=False)
        monkeypatch.setattr(_eval_api_adapter, "load_api_key", lambda: "key")

        transport = _eval_api_adapter._default_transport_factory(max_tokens=333)

        assert isinstance(transport, _eval_api_adapter._AnthropicTransport)
        assert transport._max_tokens == 333
