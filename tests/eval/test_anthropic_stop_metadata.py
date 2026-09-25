"""Tests for REQ-037: stop metadata from Claude responses in the eval adapter.

Covers `_anthropic_api.classify_termination`, `parse_message_response`,
`call_api`/`call_api_response`, the `_eval_api_adapter` refusal/token-limit
error path and `max_tokens` pass-through, and the two evaluators
(`eval-rule-activation.py`, `eval-prompt-change.py`) that must not score a
refusal or a token-limit cutoff as an answer.

Offline only: no network. urllib is mocked the same way
`tests/eval/test_providers.py` mocks it (a `_Resp(io.BytesIO)` context
manager standing in for `urlopen`'s return value).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _anthropic_api
    import _eval_api_adapter
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH


def _load_hyphenated_module(name: str, filename: str) -> Any:
    """Load a hyphenated eval script as an importable module.

    Mirrors the loader in `tests/eval/test_eval_rule_activation.py` and
    `tests/eval/test_eval_prompt_change.py`: the script imports sibling
    modules with plain `from X import Y`, so `_EVAL_DIR` must be on
    `sys.path` while it loads.
    """
    path_added = str(_EVAL_DIR) not in sys.path
    if path_added:
        sys.path.insert(0, str(_EVAL_DIR))
    try:
        spec = importlib.util.spec_from_file_location(name, _EVAL_DIR / filename)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if path_added and str(_EVAL_DIR) in sys.path:
            sys.path.remove(str(_EVAL_DIR))


rule_activation_mod = _load_hyphenated_module(
    "eval_rule_activation_stop", "eval-rule-activation.py"
)
prompt_change_mod = _load_hyphenated_module("eval_prompt_change_stop", "eval-prompt-change.py")


class _Resp(io.BytesIO):
    """Stand-in for `urllib.request.urlopen`'s context-managed return value."""

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _payload_response(payload: dict[str, Any]) -> _Resp:
    return _Resp(json.dumps(payload).encode())


# ---------------------------------------------------------------------------
# classify_termination
# ---------------------------------------------------------------------------


class TestClassifyTermination:
    @pytest.mark.parametrize("stop_reason", ["end_turn", "stop_sequence"])
    def test_completed_stop_reasons(self, stop_reason: str) -> None:
        assert _anthropic_api.classify_termination(stop_reason) == "completed"

    def test_refusal(self) -> None:
        assert _anthropic_api.classify_termination("refusal") == "refusal"

    @pytest.mark.parametrize("stop_reason", ["max_tokens", "model_context_window_exceeded"])
    def test_token_limit_stop_reasons(self, stop_reason: str) -> None:
        assert _anthropic_api.classify_termination(stop_reason) == "token_limit"

    @pytest.mark.parametrize("stop_reason", ["tool_use", "pause_turn", "some_future_reason"])
    def test_unrecognized_string_is_incomplete(self, stop_reason: str) -> None:
        assert _anthropic_api.classify_termination(stop_reason) == "incomplete"

    def test_missing_stop_reason_is_unknown(self) -> None:
        assert _anthropic_api.classify_termination(None) == "unknown"

    @pytest.mark.parametrize("stop_reason", [42, 3.14, ["end_turn"], {"reason": "end_turn"}, True])
    def test_non_string_stop_reason_is_unknown(self, stop_reason: object) -> None:
        assert _anthropic_api.classify_termination(stop_reason) == "unknown"


# ---------------------------------------------------------------------------
# parse_message_response
# ---------------------------------------------------------------------------


class TestParseMessageResponse:
    def test_end_turn_returns_completed_and_text(self) -> None:
        response = _anthropic_api.parse_message_response(
            {"content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn"}
        )
        assert response.termination == "completed"
        assert response.text == "hello"
        assert response.stop_reason == "end_turn"
        assert response.block_types == ("text",)
        assert response.blocks_scoring is False

    def test_refusal_with_stop_details_reads_category_and_explanation(self) -> None:
        response = _anthropic_api.parse_message_response(
            {
                "content": [],
                "stop_reason": "refusal",
                "stop_details": {"category": "policy", "explanation": "declined"},
            }
        )
        assert response.termination == "refusal"
        assert response.refusal_category == "policy"
        assert response.refusal_explanation == "declined"
        assert response.blocks_scoring is True

    def test_refusal_with_null_stop_details_has_no_refusal_fields(self) -> None:
        response = _anthropic_api.parse_message_response(
            {"content": [], "stop_reason": "refusal", "stop_details": None}
        )
        assert response.termination == "refusal"
        assert response.refusal_category is None
        assert response.refusal_explanation is None

    def test_refusal_with_missing_stop_details_key_has_no_refusal_fields(self) -> None:
        response = _anthropic_api.parse_message_response({"content": [], "stop_reason": "refusal"})
        assert response.termination == "refusal"
        assert response.refusal_category is None
        assert response.refusal_explanation is None

    def test_refusal_stop_details_with_non_string_fields_are_dropped(self) -> None:
        response = _anthropic_api.parse_message_response(
            {
                "content": [],
                "stop_reason": "refusal",
                "stop_details": {"category": 1, "explanation": None},
            }
        )
        assert response.refusal_category is None
        assert response.refusal_explanation is None

    def test_max_tokens_stop_reason_is_token_limit(self) -> None:
        response = _anthropic_api.parse_message_response(
            {"content": [{"type": "text", "text": "cut off"}], "stop_reason": "max_tokens"}
        )
        assert response.termination == "token_limit"
        assert response.blocks_scoring is True

    def test_max_tokens_with_only_thinking_blocks_has_empty_text(self) -> None:
        response = _anthropic_api.parse_message_response(
            {
                "content": [{"type": "thinking", "thinking": "reasoning..."}],
                "stop_reason": "max_tokens",
            }
        )
        assert response.text == ""
        assert response.termination == "token_limit"
        assert response.block_types == ("thinking",)

    def test_mixed_thinking_and_text_blocks_preserve_order_and_join_text_only(self) -> None:
        response = _anthropic_api.parse_message_response(
            {
                "content": [
                    {"type": "thinking", "thinking": "reasoning..."},
                    {"type": "text", "text": "first"},
                    {"type": "text", "text": "second"},
                ],
                "stop_reason": "end_turn",
            }
        )
        assert response.block_types == ("thinking", "text", "text")
        assert response.text == "first\nsecond"

    @pytest.mark.parametrize("stop_reason", ["tool_use", "pause_turn", "weird_new_reason"])
    def test_unrecognized_stop_reason_is_incomplete(self, stop_reason: str) -> None:
        response = _anthropic_api.parse_message_response(
            {"content": [], "stop_reason": stop_reason}
        )
        assert response.termination == "incomplete"
        # REQ-037 Failure Modes: an unrecognized stop reason must not be
        # scored as a completed answer, same as a refusal or a token_limit.
        assert response.blocks_scoring is True

    def test_missing_stop_reason_is_unknown(self) -> None:
        response = _anthropic_api.parse_message_response({"content": []})
        assert response.termination == "unknown"
        assert response.stop_reason is None

    def test_non_string_stop_reason_is_unknown(self) -> None:
        response = _anthropic_api.parse_message_response(
            {"content": [], "stop_reason": 42}
        )
        assert response.termination == "unknown"
        assert response.stop_reason is None

    def test_non_dict_content_blocks_are_skipped(self) -> None:
        response = _anthropic_api.parse_message_response(
            {
                "content": ["not-a-block", {"type": "text", "text": "kept"}],
                "stop_reason": "end_turn",
            }
        )
        assert response.block_types == ("text",)
        assert response.text == "kept"


# ---------------------------------------------------------------------------
# call_api / call_api_response
# ---------------------------------------------------------------------------


class TestCallApiTextView:
    def test_returns_identical_text_to_historical_join(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = {
            "content": [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
            ],
            "stop_reason": "end_turn",
        }
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda req, timeout=None: _payload_response(payload)
        )
        result = _anthropic_api.call_api("key", [{"role": "user", "content": "x"}], model="claude")
        assert result == "first\nsecond"

    def test_writes_termination_and_stop_reason_into_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = {"content": [{"type": "text", "text": "hi"}], "stop_reason": "max_tokens"}
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda req, timeout=None: _payload_response(payload)
        )
        metadata: dict[str, object] = {}
        _anthropic_api.call_api(
            "key", [{"role": "user", "content": "x"}], model="claude", metadata=metadata
        )
        assert metadata["termination"] == "token_limit"
        assert metadata["stop_reason"] == "max_tokens"
        assert "refusal_category" not in metadata

    def test_writes_refusal_category_into_metadata(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {
            "content": [],
            "stop_reason": "refusal",
            "stop_details": {"category": "policy", "explanation": "declined"},
        }
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda req, timeout=None: _payload_response(payload)
        )
        metadata: dict[str, object] = {}
        _anthropic_api.call_api(
            "key", [{"role": "user", "content": "x"}], model="claude", metadata=metadata
        )
        assert metadata["termination"] == "refusal"
        assert metadata["refusal_category"] == "policy"

    def test_no_metadata_arg_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda req, timeout=None: _payload_response(payload)
        )
        result = _anthropic_api.call_api("key", [{"role": "user", "content": "x"}], model="claude")
        assert result == "ok"

    def test_non_default_provider_writes_unknown_termination(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import _providers

        class _Stub:
            def complete(self, **kwargs: object) -> str:
                return "routed text"

        monkeypatch.setattr(_providers, "resolve_provider", lambda name: _Stub())
        metadata: dict[str, object] = {}
        result = _anthropic_api.call_api(
            "ignored-key",
            [{"role": "user", "content": "x"}],
            model="gpt-4o",
            provider="openai",
            metadata=metadata,
        )
        assert result == "routed text"
        assert metadata["termination"] == "unknown"
        assert metadata["stop_reason"] is None


class TestMaxTokensPassThrough:
    def test_call_api_puts_max_tokens_in_request_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(req: object, timeout: float | None = None) -> _Resp:
            captured["request"] = req
            payload = {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
            return _payload_response(payload)

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        _anthropic_api.call_api(
            "key", [{"role": "user", "content": "x"}], model="claude", max_tokens=321
        )
        request = captured["request"]
        body = json.loads(request.data.decode())
        assert body["max_tokens"] == 321


def _historical_text_join(payload: dict[str, Any]) -> str:
    """The pre-REQ-037 `call_api` body, verbatim (see git history of
    `_anthropic_api.py`): `"\\n".join(block["text"] for block in
    result.get("content", []) if block.get("type") == "text")`. Used as the
    ground truth AC-5 requires `call_api` to keep matching for every shape.
    """
    return "\n".join(
        b["text"] for b in payload.get("content", []) if b.get("type") == "text"
    )


class TestCallApiByteIdentity:
    """REQ-037 AC-5: `call_api` returns the same text as before for every
    response shape. Parametrized over the shapes DESIGN-035 calls out plus
    the two empty-input edge cases (empty `content`, missing `content`)."""

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param(
                {
                    "content": [
                        {"type": "text", "text": "first"},
                        {"type": "text", "text": "second"},
                    ],
                    "stop_reason": "end_turn",
                },
                id="two_text_blocks",
            ),
            pytest.param(
                {
                    "content": [
                        {"type": "thinking", "thinking": "reasoning..."},
                        {"type": "text", "text": "answer"},
                    ],
                    "stop_reason": "end_turn",
                },
                id="thinking_and_text",
            ),
            pytest.param(
                {
                    "content": [{"type": "thinking", "thinking": "reasoning..."}],
                    "stop_reason": "max_tokens",
                },
                id="thinking_only",
            ),
            pytest.param({"content": [], "stop_reason": "end_turn"}, id="empty_content_list"),
            pytest.param({"stop_reason": "end_turn"}, id="missing_content_key"),
            pytest.param(
                {
                    "content": [
                        {"type": "text", "text": ""},
                        {"type": "text", "text": ""},
                    ],
                    "stop_reason": "end_turn",
                },
                id="text_blocks_with_empty_strings",
            ),
        ],
    )
    def test_call_api_matches_historical_text_join(
        self, monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
    ) -> None:
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda req, timeout=None: _payload_response(payload)
        )
        result = _anthropic_api.call_api("key", [{"role": "user", "content": "x"}], model="claude")
        assert result == _historical_text_join(payload)


# ---------------------------------------------------------------------------
# _eval_api_adapter: refusal / token_limit / incomplete are errors, never retried
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# eval-rule-activation.py: refusal / token_limit judge responses are not scored
# ---------------------------------------------------------------------------


class TestRuleActivationJudgeTermination:
    SCENARIO: dict[str, Any] = {
        "desc": "d",
        "rationale": "r",
        "expected_signals": ["signal"],
        "expected_gate": "",
    }

    def _patch_call_api(self, monkeypatch: pytest.MonkeyPatch, termination: str) -> None:
        def fake(api_key, messages, model=None, seed=None, metadata=None):
            if metadata is not None:
                metadata["termination"] = termination
            return "irrelevant raw text"

        monkeypatch.setattr(rule_activation_mod, "_call_api", fake)

    def test_refusal_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_call_api(monkeypatch, "refusal")

        result = rule_activation_mod.score_response("key", self.SCENARIO, "response")

        assert result["judge_failed"] is True
        assert result["activation_score"] == 0
        assert result["termination"] == "refusal"
        assert "termination=refusal" in result["reasoning"]

    def test_token_limit_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_call_api(monkeypatch, "token_limit")

        result = rule_activation_mod.score_response("key", self.SCENARIO, "response")

        assert result["judge_failed"] is True
        assert result["activation_score"] == 0
        assert result["termination"] == "token_limit"

    def test_incomplete_is_not_scored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_call_api(monkeypatch, "incomplete")

        result = rule_activation_mod.score_response("key", self.SCENARIO, "response")

        assert result["judge_failed"] is True
        assert result["activation_score"] == 0
        assert result["termination"] == "incomplete"

    def test_completed_is_scored_normally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(api_key, messages, model=None, seed=None, metadata=None):
            if metadata is not None:
                metadata["termination"] = "completed"
            return json.dumps(
                {"activation_score": 4, "citation_score": 3, "behavior_score": 5}
            )

        monkeypatch.setattr(rule_activation_mod, "_call_api", fake)

        result = rule_activation_mod.score_response("key", self.SCENARIO, "response")

        assert result["judge_failed"] is False
        assert result["activation_score"] == 4
        assert result["termination"] == "completed"


# ---------------------------------------------------------------------------
# eval-prompt-change.py: refusal / token_limit judge responses are not scored
# ---------------------------------------------------------------------------


class TestPromptChangeJudgeTermination:
    SCENARIO: dict[str, Any] = {
        "id": "S1",
        "desc": "d",
        "input": "i",
        "expected_verdict": "ROUTE",
        "verdict_options": ["ROUTE", "DELEGATE"],
    }

    def _patch_call_api(self, monkeypatch: pytest.MonkeyPatch, termination: str) -> None:
        def fake(api_key, messages, system, model, max_tokens, metadata=None):
            if metadata is not None:
                metadata["termination"] = termination
            return "irrelevant raw text"

        monkeypatch.setattr(prompt_change_mod, "call_api", fake)

    def test_refusal_is_flagged_not_scored_not_an_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_call_api(monkeypatch, "refusal")

        out = prompt_change_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")

        assert out["verdict"] == "NOT_SCORED"
        assert out["not_scored"] is True
        assert out["termination"] == "refusal"
        assert "termination=refusal" in out["reason"]
        # `not_scored` is the flag scoring reads; `check_scenario_pass`
        # returns False unconditionally on it (REQ-037 AC-9).
        assert prompt_change_mod.check_scenario_pass(out, self.SCENARIO) is False

    def test_token_limit_is_flagged_not_scored_not_an_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_call_api(monkeypatch, "token_limit")

        out = prompt_change_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")

        assert out["verdict"] == "NOT_SCORED"
        assert out["not_scored"] is True
        assert out["termination"] == "token_limit"
        assert prompt_change_mod.check_scenario_pass(out, self.SCENARIO) is False

    def test_incomplete_is_flagged_not_scored_not_an_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_call_api(monkeypatch, "incomplete")

        out = prompt_change_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")

        assert out["verdict"] == "NOT_SCORED"
        assert out["not_scored"] is True
        assert out["termination"] == "incomplete"
        assert prompt_change_mod.check_scenario_pass(out, self.SCENARIO) is False

    def test_completed_is_scored_normally(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(api_key, messages, system, model, max_tokens, metadata=None):
            if metadata is not None:
                metadata["termination"] = "completed"
            return '{"verdict": "ROUTE", "reason": "ok"}'

        monkeypatch.setattr(prompt_change_mod, "call_api", fake)

        out = prompt_change_mod.judge_scenario("k", "sys", self.SCENARIO, "claude")

        assert out["verdict"] == "ROUTE"
        assert out["not_scored"] is False
        assert out["termination"] == "completed"
        assert prompt_change_mod.check_scenario_pass(out, self.SCENARIO) is True

    @pytest.mark.parametrize("sneaky_expected_verdict", ["ERROR", "NOT_SCORED"])
    def test_a_scenario_naming_the_sentinel_as_expected_verdict_cannot_pass_on_refusal(
        self, monkeypatch: pytest.MonkeyPatch, sneaky_expected_verdict: str
    ) -> None:
        """A scenario whose `expected_verdict` happens to equal a sentinel
        display label must not pass just because the judge was refused."""
        self._patch_call_api(monkeypatch, "refusal")
        scenario = dict(self.SCENARIO, expected_verdict=sneaky_expected_verdict)

        out = prompt_change_mod.judge_scenario("k", "sys", scenario, "claude")

        assert prompt_change_mod.check_scenario_pass(out, scenario) is False


# ---------------------------------------------------------------------------
# eval-prompt-change.py: run_scenario_multi excludes not_scored runs (REQ-037)
# ---------------------------------------------------------------------------


class TestPromptChangeNotScoredAggregation:
    SCENARIO: dict[str, Any] = {
        "id": "S1",
        "desc": "d",
        "input": "i",
        "expected_verdict": "ROUTE",
        "verdict_options": ["ROUTE", "DELEGATE"],
    }

    def _stub_judge(self, monkeypatch: pytest.MonkeyPatch, results: list[dict[str, Any]]) -> None:
        idx = {"i": 0}

        def fake(api_key, prompt, scenario, model):
            result = results[idx["i"] % len(results)]
            idx["i"] += 1
            return dict(result)

        monkeypatch.setattr(prompt_change_mod, "judge_scenario", fake)
        monkeypatch.setattr(prompt_change_mod.time, "sleep", lambda _s: None)

    def test_one_refused_of_three_with_two_passes_still_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._stub_judge(
            monkeypatch,
            [
                {"verdict": "ROUTE", "reason": "ok", "not_scored": False},
                {"verdict": "ROUTE", "reason": "ok", "not_scored": False},
                {
                    "verdict": "NOT_SCORED",
                    "reason": "termination=refusal",
                    "not_scored": True,
                },
            ],
        )

        out = prompt_change_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 3)

        assert out["passed"] is True
        assert out["runs"] == 2
        assert out["requested_runs"] == 3
        assert out["not_scored_runs"] == 1
        assert out["passes"] == 2

    def test_all_three_refused_cannot_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_judge(
            monkeypatch,
            [
                {
                    "verdict": "NOT_SCORED",
                    "reason": "termination=refusal",
                    "not_scored": True,
                }
            ]
            * 3,
        )

        out = prompt_change_mod.run_scenario_multi("k", "p", self.SCENARIO, "m", 3)

        assert out["passed"] is False
        assert out["runs"] == 0
        assert out["not_scored_runs"] == 3
        assert out["pass_rate"] == 0.0
