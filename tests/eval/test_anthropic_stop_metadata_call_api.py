"""Tests for REQ-037: `_anthropic_api.call_api` text view, `max_tokens`
pass-through, and the AC-5 byte-identity guarantee.

Split out of `test_anthropic_stop_metadata.py` (taste-lints file-size gate);
see `_anthropic_stop_metadata_test_support.py` for the shared loader and
urllib mock double.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.eval._anthropic_stop_metadata_test_support import (
    FakeUrlopenResponse,
    _anthropic_api,
    payload_response,
)

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
            "urllib.request.urlopen", lambda req, timeout=None: payload_response(payload)
        )
        result = _anthropic_api.call_api("key", [{"role": "user", "content": "x"}], model="claude")
        assert result == "first\nsecond"

    def test_writes_termination_and_stop_reason_into_metadata(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = {"content": [{"type": "text", "text": "hi"}], "stop_reason": "max_tokens"}
        monkeypatch.setattr(
            "urllib.request.urlopen", lambda req, timeout=None: payload_response(payload)
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
            "urllib.request.urlopen", lambda req, timeout=None: payload_response(payload)
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
            "urllib.request.urlopen", lambda req, timeout=None: payload_response(payload)
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

        def fake_urlopen(req: object, timeout: float | None = None) -> FakeUrlopenResponse:
            captured["request"] = req
            payload = {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
            return payload_response(payload)

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
    return "\n".join(b["text"] for b in payload.get("content", []) if b.get("type") == "text")


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
            "urllib.request.urlopen", lambda req, timeout=None: payload_response(payload)
        )
        result = _anthropic_api.call_api("key", [{"role": "user", "content": "x"}], model="claude")
        assert result == _historical_text_join(payload)
