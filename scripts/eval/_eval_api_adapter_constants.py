"""Constants for the eval API adapter."""

from __future__ import annotations

import re

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
    return require_str_or_none(value, "system_fingerprint")


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
