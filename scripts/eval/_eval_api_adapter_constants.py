"""Constants for the eval API adapter."""

from __future__ import annotations

import re

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
    """Normalize a raw system_fingerprint value to the three-state contract.

    Three states:
    - present-and-valid: value is a non-None str -> returned as-is
    - absent: value is None -> returned as None
    - present-but-malformed: value is non-str, non-None -> returned as a
      sentinel string ``"<malformed:TYPENAME>"`` so downstream can distinguish
      this from legitimate absence and flag provider drift

    Rationale: silent coercion (``x if isinstance(x, str) else None``) maps
    malformed to absent, defeating the existing guard in _run_persistence.py
    that checks for an unexpected type. A malformed fingerprint means the
    provider changed its response shape, which is exactly the drift that guard
    exists to detect. Recording a distinct sentinel surfaces the drift.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return f"<malformed:{type(value).__name__}>"


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
