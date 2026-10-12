"""Billing and provider error type reporting for redacted HTTP errors (issue #6138)."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import NoReturn

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(EVAL_DIR))
try:
    import _anthropic_api
    import _eval_common
    import _providers
finally:
    sys.path[:] = ORIGINAL_SYS_PATH

CREDIT_MESSAGE = "Your credit balance is too low to access the Anthropic API."
SECRET = "ghp_" + "K" * 36
FREE_TEXT = "private free text from the provider"


def _body(error_type: str, message: str) -> bytes:
    return json.dumps({"type": "error", "error": {"type": error_type, "message": message}}).encode()


def test_credit_balance_400_reports_billing_with_error_type() -> None:
    message = _eval_common.safe_http_error_message(
        "Anthropic API", 400, _body("invalid_request_error", CREDIT_MESSAGE)
    )

    assert message == (
        "Anthropic API returned HTTP 400: error=billing; "
        "provider_error_type=invalid_request_error; provider response redacted"
    )
    assert CREDIT_MESSAGE not in message


def test_other_400_keeps_client_error_and_appends_error_type() -> None:
    message = _eval_common.safe_http_error_message(
        "Anthropic API", 400, _body("invalid_request_error", FREE_TEXT)
    )

    assert message == (
        "Anthropic API returned HTTP 400: error=client_error; "
        "provider_error_type=invalid_request_error; provider response redacted"
    )
    assert FREE_TEXT not in message


@pytest.mark.parametrize("body", [None, b"", b"{not json", b"[1, 2]", b'"text"', b"null"])
def test_missing_or_malformed_body_keeps_the_fixed_message(body: object) -> None:
    message = _eval_common.safe_http_error_message("Anthropic API", 400, body)

    assert (
        message == "Anthropic API returned HTTP 400: error=client_error; provider response redacted"
    )


def test_malformed_json_carrying_the_phrase_still_reports_billing() -> None:
    message = _eval_common.safe_http_error_message(
        "Anthropic API", 400, f"<html>{CREDIT_MESSAGE}</html>"
    )

    assert "error=billing" in message
    assert "<html>" not in message


def test_unlisted_error_type_is_dropped() -> None:
    message = _eval_common.safe_http_error_message(
        "Anthropic API", 400, _body(f"evil {SECRET}", FREE_TEXT)
    )

    assert SECRET not in message
    assert "provider_error_type" not in message
    assert "error=client_error" in message


def test_non_string_error_type_and_message_are_ignored() -> None:
    body = json.dumps({"error": {"type": ["invalid_request_error"], "message": 7}}).encode()

    message = _eval_common.safe_http_error_message("Anthropic API", 400, body)

    assert (
        message == "Anthropic API returned HTTP 400: error=client_error; provider response redacted"
    )


def test_credit_phrase_outside_a_400_does_not_report_billing() -> None:
    message = _eval_common.safe_http_error_message(
        "Anthropic API", 500, _body("api_error", CREDIT_MESSAGE)
    )

    assert "error=server_error" in message
    assert "provider_error_type=api_error" in message


def test_billing_error_type_reports_billing_at_any_status() -> None:
    message = _eval_common.safe_http_error_message(
        "Anthropic API", 402, _body("billing_error", FREE_TEXT)
    )

    assert message == (
        "Anthropic API returned HTTP 402: error=billing; "
        "provider_error_type=billing_error; provider response redacted"
    )


def test_openai_style_inner_object_body_is_read() -> None:
    body = {"type": "invalid_request_error", "message": CREDIT_MESSAGE}

    message = _eval_common.safe_http_error_message("OpenAI API", 400, body)

    assert "error=billing" in message
    assert "provider_error_type=invalid_request_error" in message


def test_oversized_body_is_truncated_before_parsing() -> None:
    padding = " " * (_eval_common._MAX_BODY_CHARS + 10)

    message = _eval_common.safe_http_error_message(
        "Anthropic API", 400, padding + _body("invalid_request_error", CREDIT_MESSAGE).decode()
    )

    assert "error=billing" not in message


@pytest.mark.parametrize(
    ("status", "category"),
    [(401, "auth"), (403, "auth"), (408, "timeout"), (429, "rate_limit"), (503, "server_error")],
)
def test_existing_categories_are_unchanged_with_a_body(status: int, category: str) -> None:
    message = _eval_common.safe_http_error_message(
        "Anthropic API", status, _body("api_error", FREE_TEXT)
    )

    assert f"error={category}" in message


def test_status_outside_http_ranges_is_http_error() -> None:
    assert "error=http_error" in _eval_common.safe_http_error_message("X", 302)


def test_is_billing_error_message_matches_only_the_billing_shape() -> None:
    billing = _eval_common.safe_http_error_message(
        "Anthropic API", 400, _body("invalid_request_error", CREDIT_MESSAGE)
    )
    other = _eval_common.safe_http_error_message("Anthropic API", 400, None)

    assert _eval_common.is_billing_error_message(billing) is True
    assert _eval_common.is_billing_error_message(other) is False
    assert _eval_common.is_billing_error_message("error=billing") is False


def _http_error(url: str, code: int, body: bytes | None) -> urllib.error.HTTPError:
    fp = io.BytesIO(body) if body is not None else None
    return urllib.error.HTTPError(url, code, "x", Message(), fp)


def test_anthropic_urllib_transport_reports_billing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(request: urllib.request.Request, timeout: float) -> NoReturn:
        raise _http_error(
            "https://api.anthropic.com/v1/messages",
            400,
            _body("invalid_request_error", CREDIT_MESSAGE),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError) as exc_info:
        _anthropic_api.call_api("key", [{"role": "user", "content": "hi"}])

    assert _eval_common.is_billing_error_message(str(exc_info.value))
    assert CREDIT_MESSAGE not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_anthropic_urllib_transport_survives_an_unreadable_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(request: urllib.request.Request, timeout: float) -> NoReturn:
        raise _http_error("https://api.anthropic.com/v1/messages", 400, None)

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError) as exc_info:
        _anthropic_api.call_api("key", [{"role": "user", "content": "hi"}])

    assert str(exc_info.value) == (
        "Anthropic API returned HTTP 400: error=client_error; provider response redacted"
    )


def test_models_endpoint_reports_billing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(request: urllib.request.Request, timeout: float) -> NoReturn:
        raise _http_error(
            "https://api.anthropic.com/v1/models",
            400,
            _body("invalid_request_error", CREDIT_MESSAGE),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError) as exc_info:
        _anthropic_api.list_available_models("key")

    assert "error=billing" in str(exc_info.value)


class _SDKError(Exception):
    status_code = 400

    def __init__(self, body: object = None, message: object = None) -> None:
        super().__init__(FREE_TEXT)
        self.body = body
        self.message = message


def test_sdk_transport_reads_billing_from_the_parsed_body() -> None:
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": CREDIT_MESSAGE}}

    with pytest.raises(RuntimeError) as exc_info:
        _providers._normalize_and_raise("Anthropic", _SDKError(body=body))

    assert str(exc_info.value) == (
        "Anthropic API returned HTTP 400: error=billing; "
        "provider_error_type=invalid_request_error; provider response redacted"
    )


def test_sdk_transport_falls_back_to_the_exception_message() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        _providers._normalize_and_raise("Anthropic", _SDKError(message=CREDIT_MESSAGE))

    assert "error=billing" in str(exc_info.value)


def test_sdk_transport_without_body_or_message_keeps_the_fixed_message() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        _providers._normalize_and_raise("Anthropic", _SDKError(message=42))

    assert str(exc_info.value) == (
        "Anthropic API returned HTTP 400: error=client_error; provider response redacted"
    )
    assert FREE_TEXT not in str(exc_info.value)
