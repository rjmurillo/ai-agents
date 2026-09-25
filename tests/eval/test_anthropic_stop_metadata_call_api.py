"""Tests for REQ-037: `_anthropic_api.call_api` text view, `max_tokens`
pass-through, and the AC-5 byte-identity guarantee.

See `_anthropic_stop_metadata_test_support.py` for the shared loader and
urllib mock double. Module functions, not classes, and `MagicMock`/
`SimpleNamespace` over nested fakes (CQA cohesion: a `def` or `class`
counts, however nested). The standalone two-text-blocks check from before
this split is now the `two_text_blocks` case below, same payload and
assertion; keeping both was duplicate coverage, not a second behavior.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from tests.eval._anthropic_stop_metadata_test_support import (
    _anthropic_api,
    payload_response,
)


def _mock_urlopen(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: payload_response(payload)
    )


_OK_PAYLOAD = {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}

# call_api metadata write-through

_REFUSAL_PAYLOAD = {
    "content": [],
    "stop_reason": "refusal",
    "stop_details": {"category": "policy", "explanation": "declined"},
}

_METADATA_CASES = [
    pytest.param(
        {"content": [{"type": "text", "text": "hi"}], "stop_reason": "max_tokens"},
        {"termination": "token_limit", "stop_reason": "max_tokens"},
        ("refusal_category",),
        id="max_tokens_writes_token_limit",
    ),
    pytest.param(
        _REFUSAL_PAYLOAD,
        {"termination": "refusal", "refusal_category": "policy"},
        (),
        id="refusal_writes_category",
    ),
]


@pytest.mark.parametrize("payload, expected, absent_keys", _METADATA_CASES)
def test_call_api_writes_metadata(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    expected: dict[str, Any],
    absent_keys: tuple[str, ...],
) -> None:
    _mock_urlopen(monkeypatch, payload)
    metadata: dict[str, object] = {}
    _anthropic_api.call_api(
        "key", [{"role": "user", "content": "x"}], model="claude", metadata=metadata
    )
    for key, value in expected.items():
        assert metadata[key] == value
    for key in absent_keys:
        assert key not in metadata


def test_call_api_no_metadata_arg_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_urlopen(monkeypatch, _OK_PAYLOAD)
    result = _anthropic_api.call_api("key", [{"role": "user", "content": "x"}], model="claude")
    assert result == "ok"


def test_call_api_non_default_provider_writes_unknown_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import _providers

    stub = SimpleNamespace(complete=lambda **kwargs: "routed text")
    monkeypatch.setattr(_providers, "resolve_provider", lambda name: stub)
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


# max_tokens pass-through


def test_call_api_puts_max_tokens_in_request_body(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_urlopen = MagicMock(return_value=payload_response(_OK_PAYLOAD))
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    _anthropic_api.call_api(
        "key", [{"role": "user", "content": "x"}], model="claude", max_tokens=321
    )

    request = mock_urlopen.call_args.args[0]
    body = json.loads(request.data.decode())
    assert body["max_tokens"] == 321


# AC-5: call_api's text view matches the pre-REQ-037 join for every shape


def _historical_text_join(payload: dict[str, Any]) -> str:
    """The pre-REQ-037 `call_api` body, verbatim (see git history of
    `_anthropic_api.py`): `"\\n".join(block["text"] for block in
    result.get("content", []) if block.get("type") == "text")`. Used as the
    ground truth AC-5 requires `call_api` to keep matching for every shape.
    """
    return "\n".join(b["text"] for b in payload.get("content", []) if b.get("type") == "text")


_TEXT = {"type": "text"}
_THINKING = {"type": "thinking", "thinking": "reasoning..."}

_BYTE_IDENTITY_CASES = [
    pytest.param(
        {
            "content": [_TEXT | {"text": "first"}, _TEXT | {"text": "second"}],
            "stop_reason": "end_turn",
        },
        id="two_text_blocks",
    ),
    pytest.param(
        {"content": [_THINKING, _TEXT | {"text": "answer"}], "stop_reason": "end_turn"},
        id="thinking_and_text",
    ),
    pytest.param({"content": [_THINKING], "stop_reason": "max_tokens"}, id="thinking_only"),
    pytest.param({"content": [], "stop_reason": "end_turn"}, id="empty_content_list"),
    pytest.param({"stop_reason": "end_turn"}, id="missing_content_key"),
    pytest.param(
        {"content": [_TEXT | {"text": ""}, _TEXT | {"text": ""}], "stop_reason": "end_turn"},
        id="text_blocks_with_empty_strings",
    ),
]


@pytest.mark.parametrize("payload", _BYTE_IDENTITY_CASES)
def test_call_api_matches_historical_text_join(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    _mock_urlopen(monkeypatch, payload)
    result = _anthropic_api.call_api("key", [{"role": "user", "content": "x"}], model="claude")
    assert result == _historical_text_join(payload)
