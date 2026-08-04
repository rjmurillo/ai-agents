"""Regression tests for provider errors that enter persisted eval artifacts."""

from __future__ import annotations

import io
import json
import sys
import traceback
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
    import _providers
finally:
    sys.path[:] = ORIGINAL_SYS_PATH


SECRET = "ghp_" + "H" * 36
PROMPT_FRAGMENT = "private fixture prompt fragment"


def _rendered_exception(error: BaseException) -> str:
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))


def _persisted_error(error: Exception) -> str:
    return json.dumps(
        {
            "reasoning": f"judge API failure: {error}",
            "error": str(error),
        }
    )


def test_anthropic_http_body_never_reaches_exception_or_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps({"token": SECRET, "prompt": PROMPT_FRAGMENT}).encode()

    def fail(request: urllib.request.Request, timeout: float) -> NoReturn:
        raise urllib.error.HTTPError(
            "https://api.anthropic.com/v1/messages",
            400,
            "Bad Request",
            Message(),
            io.BytesIO(body),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError) as exc_info:
        _anthropic_api.call_api(
            "key",
            [{"role": "user", "content": PROMPT_FRAGMENT}],
        )

    combined = _rendered_exception(exc_info.value) + _persisted_error(exc_info.value)
    assert SECRET not in combined
    assert PROMPT_FRAGMENT not in combined
    assert exc_info.value.__cause__ is None
    assert str(exc_info.value) == (
        "Anthropic API returned HTTP 400: error=client_error; provider response redacted"
    )


class _SDKHTTPError(Exception):
    status_code = 429

    def __str__(self) -> str:
        return json.dumps({"token": SECRET, "prompt": PROMPT_FRAGMENT})


def test_sdk_http_body_never_reaches_exception_or_json() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        _providers._normalize_and_raise("OpenAI", _SDKHTTPError())

    combined = _rendered_exception(exc_info.value) + _persisted_error(exc_info.value)
    assert SECRET not in combined
    assert PROMPT_FRAGMENT not in combined
    assert exc_info.value.__cause__ is None
    assert str(exc_info.value) == (
        "OpenAI API returned HTTP 429: error=rate_limit; provider response redacted"
    )


def test_models_endpoint_http_body_never_reaches_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps({"token": SECRET, "prompt": PROMPT_FRAGMENT}).encode()

    def fail(request: urllib.request.Request, timeout: float) -> NoReturn:
        raise urllib.error.HTTPError(
            "https://api.anthropic.com/v1/models",
            503,
            "Unavailable",
            Message(),
            io.BytesIO(body),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError) as exc_info:
        _anthropic_api.list_available_models("key")

    combined = _rendered_exception(exc_info.value) + _persisted_error(exc_info.value)
    assert SECRET not in combined
    assert PROMPT_FRAGMENT not in combined
    assert exc_info.value.__cause__ is None
    assert str(exc_info.value) == (
        "Anthropic models endpoint returned HTTP 503: error=server_error; "
        "provider response redacted"
    )
