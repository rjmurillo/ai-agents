"""Constants for the eval API adapter."""

from __future__ import annotations

import re
from typing import cast

from _eval_common import require_str_or_none

ERR_RATE_LIMIT: str = "rate_limit"
ERR_SERVER_ERROR: str = "server_error"
ERR_TIMEOUT: str = "timeout"
ERR_CLIENT_ERROR: str = "client_error"
ERR_AUTH: str = "auth"
ERR_UNKNOWN: str = "unknown"
ERR_TOTAL_TIMEOUT: str = "timeout_total"

DEFAULT_MAX_RETRIES: int = 3
BACKOFF_BASE_SEC: float = 1.0
BACKOFF_MAX_SEC: float = 30.0
DEFAULT_TOTAL_TIMEOUT_SEC: float = 180.0

HTTP_STATUS_RE = re.compile(r"HTTP (\d{3})")
TIMEOUT_HINT: str = "timed out"
RATE_LIMIT_HINT: str = "rate limit"
AUTH_HINT_RE = re.compile(
    r"(authentication failed|not logged in|not signed in|please (?:log|sign) in|login required)",
    re.IGNORECASE,
)

ALLOWED_LOG_FIELDS: frozenset[str] = frozenset(
    {
        "fixture_id",
        "variant",
        "run_index",
        "model_id",
        "attempt",
        "outcome",
        "latency_ms",
        "tokens_in",
        "tokens_out",
        "error_category",
    }
)


def normalize_fingerprint(value: object) -> str | None:
    """Apply the shared string-or-absence provider metadata policy."""
    return cast(str | None, require_str_or_none(value, "system_fingerprint"))


BANNED_LOG_FIELDS: frozenset[str] = frozenset(
    {
        "api_key",
        "authorization",
        "headers",
        "messages",
        "payload",
        "prompt",
        "raw_error",
        "raw_response",
        "request_body",
        "response_body",
        "secret",
        "system",
        "token",
    }
)


def categorize_error(exc: Exception) -> str:
    """Translate a provider RuntimeError into an error_category.

    `_anthropic_api.call_api` raises one of three well-known message shapes
    (see `_anthropic_api.py`): HTTP error, timeout, or other URLError.
    Subprocess-backed providers have no HTTP status at all, so their failures
    are read from text instead. Anything unrecognized falls back to the
    transient default, which retries rather than discarding a sample.

    A status, when the message carries one, outranks any text hint. The HTTP
    error shape appends the sanitized response body, so a 4xx whose body
    happens to say "timed out" would otherwise be read as a timeout and
    retried, contradicting the no-retry rule this module documents for
    non-transient 4xx. Text hints are the fallback for the providers that
    report no status at all, which is the only population they were chosen to
    describe.
    """
    message = str(exc)
    match = HTTP_STATUS_RE.search(message)
    if match is None:
        # No HTTP status. Check the text signals a subprocess provider can
        # give, then treat the rest as a transient network issue.
        if TIMEOUT_HINT in message:
            return ERR_TIMEOUT
        if RATE_LIMIT_HINT in message.lower():
            return ERR_RATE_LIMIT
        if AUTH_HINT_RE.search(message):
            return ERR_AUTH
        return ERR_SERVER_ERROR
    code = int(match.group(1))
    if code in (401, 403):
        return ERR_AUTH
    if code == 408:
        return ERR_TIMEOUT
    if code == 429:
        return ERR_RATE_LIMIT
    if 500 <= code < 600:
        return ERR_SERVER_ERROR
    if 400 <= code < 500:
        return ERR_CLIENT_ERROR
    return cast(str, ERR_UNKNOWN)


# Retried = transient. Anything else is recorded once and not retried.
TRANSIENT: frozenset[str] = frozenset({ERR_RATE_LIMIT, ERR_SERVER_ERROR, ERR_TIMEOUT})


def is_transient(category: str) -> bool:
    return category in TRANSIENT
