"""Transport tests for scripts/metrics/sg_reference_ab_api.py (#5856).

Covers the https-only opener, the non-https guard, and retry timing. Split from
``test_sg_reference_ab_api.py`` to keep each test file under 500 lines. Every
test patches the opener or calls a pure helper; none reaches the network.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.metrics import sg_reference_ab_api as api
from tests.metrics.sg_reference_ab_helpers import make_fake_urlopen, record_sleeps


def test_post_messages_retries_once_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = make_fake_urlopen(
        [urllib.error.URLError("connection reset"), {"content": [], "usage": {}}]
    )
    monkeypatch.setattr(api._HTTPS_OPENER, "open", fake)
    slept = record_sleeps(monkeypatch)

    assert api.post_messages("key", "model", "system", [], []) == {"content": [], "usage": {}}
    assert len(calls) == 2
    assert len(slept) == 1


def _http_error_with_headers(code: int, headers: dict[str, str] | None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.anthropic.com/v1/messages", code, "err", cast(Any, headers), None
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_http_error_with_headers(429, {"Retry-After": "7"}), 7.0),
        (_http_error_with_headers(429, {"Retry-After": " 999 "}), api.RETRY_MAX_DELAY_S),
        (_http_error_with_headers(503, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), 2.0),
        (_http_error_with_headers(503, None), 2.0),
        (_http_error_with_headers(502, {}), 2.0),
        (urllib.error.URLError("dns"), 2.0),
        (TimeoutError("slow"), 2.0),
    ],
)
def test_retry_delay_s_for_retryable_errors(exc: Exception, expected: float) -> None:
    assert api.retry_delay_s(exc, jitter=0.5) == expected


@pytest.mark.parametrize(
    "exc", [_http_error_with_headers(400, {"Retry-After": "1"}), ValueError("not transport")]
)
def test_retry_delay_s_returns_none_for_non_retryable_errors(exc: Exception) -> None:
    assert api.retry_delay_s(exc, jitter=0.5) is None


def test_retry_delay_s_jitter_scales_the_base_delay() -> None:
    low = api.retry_delay_s(urllib.error.URLError("x"), jitter=0.0)
    high = api.retry_delay_s(urllib.error.URLError("x"), jitter=0.99)
    assert low == api.RETRY_BASE_DELAY_S * 0.5
    assert high is not None and high > api.RETRY_BASE_DELAY_S


def test_send_once_refuses_a_non_https_url(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = make_fake_urlopen([{"content": []}])
    monkeypatch.setattr(api._HTTPS_OPENER, "open", fake)
    request = urllib.request.Request("file:///etc/passwd")

    with pytest.raises(ValueError, match="non-https"):
        api._send_once(request)
    assert calls == []


def test_https_opener_has_no_file_handler_and_cannot_open_file_urls(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("do not read", encoding="utf-8")

    with pytest.raises(urllib.error.URLError, match="unknown url type"):
        api._HTTPS_OPENER.open(secret.as_uri())
