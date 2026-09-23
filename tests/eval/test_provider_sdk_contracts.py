"""Contract tests for the SDK-backed eval providers.

Guards the seam a dependency upgrade can break silently: `anthropic` and
`openai` are typed SDKs, and a version bump can rename, retype, or drop a
keyword `_http_providers.py` / `_anthropic_api.py` pass to `messages.create`
/ `chat.completions.create`. The Anthropic tests run against the REAL
installed `anthropic` package (a core dependency, always present) through
its own HTTP transport mock (`httpx2.MockTransport`), not a hand-rolled fake
class, so a real signature change fails here instead of passing a fake that
does not know the SDK changed. The OpenAI tests do the same through the real
`openai` package's own transport (`httpx.MockTransport`) when that optional
extra is installed; they skip otherwise (`pytest.importorskip`), matching
the no-openai-required convention `tests/eval/test_providers.py` documents.

Reproduces the reported bug: `anthropic` 1.6.0 dropped `temperature` from
every `messages.create` overload. `_AnthropicSDKProvider.complete` used to
pass it as a direct keyword and got
`TypeError: Messages.create() got an unexpected keyword argument
'temperature'`, which `_normalize_and_raise` mislabeled as a network
failure. The fix sends `temperature` through `extra_body` instead (bypasses
the typed schema) and retries once without it on the documented 400 body
(live wording confirmed against claude-sonnet-5: `` `temperature` is
deprecated for this model. ``), sharing that retry decision with the
urllib transport in `_anthropic_api.py` through
`_eval_common.call_with_temperature_fallback`.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import TracebackType
from typing import Any, cast

import anthropic
import httpx2
import pytest

# Captured before any test monkeypatches `anthropic.Anthropic` to a stub
# that returns a premade mock-transport client; building that client calls
# the real class, not whatever the patch currently points at.
_RealAnthropic = anthropic.Anthropic

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _anthropic_api
    import _eval_common
    import _eval_errors
    import _http_providers
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH

# Wording confirmed live against claude-sonnet-5 on 2026-09-23: the API
# quotes the field with backticks and ends the sentence with a period.
DEPRECATED_ERROR_BODY: dict[str, object] = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "`temperature` is deprecated for this model.",
    },
}


def _ok_message_body(text: str = "ok") -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


@pytest.fixture(autouse=True)
def _anthropic_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")


def _mock_anthropic_client(handler: Any) -> anthropic.Anthropic:
    return _RealAnthropic(
        api_key="sk-test-key",
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    )


# --- Anthropic SDK contract (real installed `anthropic` package) --------


def test_sdk_provider_sends_temperature_via_extra_body_when_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`messages.create` must accept every keyword the provider passes.

    This is the direct regression guard for the reported bug: the old code
    passed `temperature` as a typed keyword and the real SDK raised
    `TypeError`. If a future edit reintroduces that, this call raises and
    the test fails.
    """
    calls: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx2.Response(200, json=_ok_message_body("accepted"))

    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: _mock_anthropic_client(handler))
    provider = _http_providers._AnthropicSDKProvider()

    text = provider.complete(
        messages=[{"role": "user", "content": "hi"}],
        system="be terse",
        model="claude-opus-4-6",
        max_tokens=32,
        temperature=0.0,
    )

    assert text == "accepted"
    assert len(calls) == 1
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["system"] == "be terse"
    assert calls[0]["max_tokens"] == 32
    assert calls[0]["model"] == "claude-opus-4-6"


def test_sdk_provider_retries_without_temperature_on_deprecated_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content.decode())
        calls.append(body)
        if "temperature" in body:
            return httpx2.Response(400, json=DEPRECATED_ERROR_BODY)
        return httpx2.Response(200, json=_ok_message_body("retried"))

    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: _mock_anthropic_client(handler))
    provider = _http_providers._AnthropicSDKProvider()

    text = provider.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="claude-sonnet-5",
        temperature=0.0,
    )

    assert text == "retried"
    assert len(calls) == 2
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]


def test_sdk_provider_omits_temperature_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """`temperature=None` (the runtime grader default) sends one request with no field."""
    calls: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx2.Response(200, json=_ok_message_body("omitted"))

    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: _mock_anthropic_client(handler))
    provider = _http_providers._AnthropicSDKProvider()

    text = provider.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="claude-sonnet-5",
        temperature=None,
    )

    assert text == "omitted"
    assert len(calls) == 1
    assert "temperature" not in calls[0]


def test_sdk_provider_does_not_retry_on_unrelated_400(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    other_error = {
        "type": "error",
        "error": {"type": "not_found_error", "message": "model: bogus-model not found"},
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(json.loads(request.content.decode()))
        return httpx2.Response(400, json=other_error)

    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: _mock_anthropic_client(handler))
    provider = _http_providers._AnthropicSDKProvider()

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="bogus-model",
            temperature=0.0,
        )

    assert len(calls) == 1  # no retry storm on an unrelated 400
    message = str(exc_info.value)
    assert "network_failure" not in message
    assert "client_error" in message


def test_sdk_provider_typeerror_is_reported_honestly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A TypeError from the SDK (any argument, not just temperature) must not
    be relabeled as a network failure. Covers a future SDK bump that drops a
    different keyword this provider still sends unconditionally."""

    class _FakeMessages:
        @staticmethod
        def create(**kwargs: object) -> object:
            if "system" in kwargs:
                raise TypeError("Messages.create() got an unexpected keyword argument 'system'")
            raise AssertionError("unreachable")  # pragma: no cover

    class _RejectsSystem:
        def __init__(self, **_: object) -> None:
            self.messages = _FakeMessages()

    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: _RejectsSystem())
    provider = _http_providers._AnthropicSDKProvider()

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="claude-sonnet-5",
            temperature=0.0,
        )

    message = str(exc_info.value)
    assert "network_failure" not in message
    assert "sdk_argument_mismatch" in message


def test_real_sdk_rejects_temperature_as_a_direct_keyword() -> None:
    """Root-cause pin. As of anthropic 1.6.0, `messages.create` has no
    `temperature` parameter on any overload; passing it directly raises
    `TypeError` regardless of model. This is why the provider sends it
    through `extra_body` instead. If a future SDK version restores
    `temperature` as a typed parameter, this test starts failing, which is
    the signal to drop the `extra_body` workaround.
    """
    client = _mock_anthropic_client(lambda request: httpx2.Response(200, json=_ok_message_body()))
    # cast: deliberately calling with an argument the typed signature does
    # not accept, to prove the SDK itself rejects it at runtime.
    create = cast("Callable[..., object]", client.messages.create)

    with pytest.raises(TypeError, match="temperature"):
        create(
            model="claude-sonnet-5",
            max_tokens=16,
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.0,
        )


# --- Shared retry decision (_eval_common) --------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("`temperature` is deprecated for this model.", True),  # live wording
        ('"temperature" is deprecated for this model', True),
        ('\\"temperature\\" is deprecated for this model', True),
        ('{"error":{"message":"\\"temperature\\" is deprecated for this model"}}', True),
        ("`TEMPERATURE` IS DEPRECATED FOR THIS MODEL.", True),
        ("temperature is deprecated for this model", True),
        ("model: bogus-model not found", False),
        ("", False),
    ],
)
def test_is_temperature_deprecated_message(message: str, expected: bool) -> None:
    assert _eval_common.is_temperature_deprecated_message(message) is expected


def test_call_with_temperature_fallback_skips_retry_on_success() -> None:
    calls: list[bool] = []

    def send(include_temperature: bool) -> str:
        calls.append(include_temperature)
        return "ok"

    result = _eval_common.call_with_temperature_fallback(send, lambda _exc: True)

    assert result == "ok"
    assert calls == [True]


def test_call_with_temperature_fallback_retries_once_on_deprecated_error() -> None:
    calls: list[bool] = []

    def send(include_temperature: bool) -> str:
        calls.append(include_temperature)
        if include_temperature:
            raise _eval_errors.TemperatureDeprecatedError
        return "retried"

    result = _eval_common.call_with_temperature_fallback(
        send, lambda exc: isinstance(exc, _eval_errors.TemperatureDeprecatedError)
    )

    assert result == "retried"
    assert calls == [True, False]


def test_call_with_temperature_fallback_propagates_unrelated_error() -> None:
    def send(include_temperature: bool) -> str:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        _eval_common.call_with_temperature_fallback(send, lambda _exc: False)


def test_call_with_temperature_fallback_propagates_second_failure() -> None:
    """A second failure (e.g. the retry itself 400s for an unrelated reason)
    must propagate, not loop or swallow the error."""
    calls: list[bool] = []

    def send(include_temperature: bool) -> str:
        calls.append(include_temperature)
        if include_temperature:
            raise _eval_errors.TemperatureDeprecatedError
        raise RuntimeError("still broken without temperature")

    with pytest.raises(RuntimeError, match="still broken without temperature"):
        _eval_common.call_with_temperature_fallback(
            send, lambda exc: isinstance(exc, _eval_errors.TemperatureDeprecatedError)
        )

    assert calls == [True, False]


# --- urllib transport (_anthropic_api.call_api) --------------------------


class _Resp(BytesIO):
    def __enter__(self) -> _Resp:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        return None


def _http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.anthropic.com/v1/messages", code, "", Message(), BytesIO(body)
    )


def _sent_body(request: urllib.request.Request) -> dict[str, object]:
    """Decode the JSON body `_anthropic_api._build_messages_request` sent.

    `Request.data` is typed as a union (`bytes | Iterable[bytes] | IO[bytes]
    | None`); every caller here always builds it with a `bytes` payload, so
    the cast narrows rather than suppresses.
    """
    return cast(dict[str, object], json.loads(cast(bytes, request.data).decode()))


def test_call_api_sends_temperature_for_models_that_accept_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> _Resp:
        calls.append(_sent_body(request))
        return _Resp(json.dumps({"content": [{"type": "text", "text": "single-call"}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    text = _anthropic_api.call_api(
        "key", [{"role": "user", "content": "hi"}], model="claude-opus-4-6", temperature=0.0
    )

    assert text == "single-call"
    assert len(calls) == 1
    assert calls[0]["temperature"] == 0.0


def test_call_api_retries_without_temperature_on_deprecated_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> _Resp:
        body = _sent_body(request)
        calls.append(body)
        if "temperature" in body:
            raise _http_error(400, json.dumps(DEPRECATED_ERROR_BODY).encode())
        return _Resp(json.dumps({"content": [{"type": "text", "text": "urllib-retried"}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    text = _anthropic_api.call_api(
        "key", [{"role": "user", "content": "hi"}], model="claude-sonnet-5", temperature=0.0
    )

    assert text == "urllib-retried"
    assert len(calls) == 2
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]


def test_call_api_omits_temperature_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> _Resp:
        calls.append(_sent_body(request))
        return _Resp(json.dumps({"content": [{"type": "text", "text": "omitted"}]}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    text = _anthropic_api.call_api(
        "key", [{"role": "user", "content": "hi"}], model="claude-sonnet-5", temperature=None
    )

    assert text == "omitted"
    assert len(calls) == 1
    assert "temperature" not in calls[0]


def test_call_api_does_not_retry_on_unrelated_400(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    other_error = {"type": "error", "error": {"message": "model not found"}}

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> _Resp:
        calls.append(_sent_body(request))
        raise _http_error(400, json.dumps(other_error).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        _anthropic_api.call_api(
            "key", [{"role": "user", "content": "hi"}], model="bogus-model", temperature=0.0
        )

    assert len(calls) == 1
    assert str(exc_info.value) == (
        "Anthropic API returned HTTP 400: error=client_error; provider response redacted"
    )


# --- OpenAI SDK contract (real installed `openai` package, optional) -----


def test_openai_provider_messages_create_accepts_every_keyword_it_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same contract as the Anthropic SDK tests above, for the sibling
    transport. Skips when the optional `eval` extra (`openai`) is not
    installed, matching `tests/eval/test_providers.py`'s no-openai-required
    convention; installing `.[eval]` locally or in CI activates it.
    """
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")

    calls: list[dict[str, object]] = []

    def handler(request: Any) -> Any:
        calls.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi"},
                        "finish_reason": "stop",
                    }
                ],
                "system_fingerprint": "fp_test",
            },
        )

    client = openai.OpenAI(
        api_key="sk-test", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(openai, "OpenAI", lambda **_: client)

    provider = _http_providers._OpenAICompatibleProvider(
        name="openai", provider_label="OpenAI", key_names=["OPENAI_API_KEY"]
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    text = provider.complete(
        messages=[{"role": "user", "content": "hi"}],
        system="be terse",
        model="gpt-4o",
        max_tokens=16,
        temperature=0.0,
        seed=7,
    )

    assert text == "hi"
    assert len(calls) == 1
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["max_tokens"] == 16
    assert calls[0]["seed"] == 7
