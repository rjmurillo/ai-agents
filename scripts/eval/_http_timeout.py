"""Per-call timeout for the OpenAI-compatible eval transport.

Kept apart from ``_http_providers`` so that module stays under the 500-line
taste limit.
"""

from __future__ import annotations

import os

DEFAULT_HTTP_TIMEOUT_SECONDS = 120.0
MAX_HTTP_TIMEOUT_SECONDS = 1800.0


def http_timeout_seconds() -> float:
    """Per-call timeout: 120s, or EVAL_HTTP_TIMEOUT_SECONDS within (0, 1800].

    A value that is not a number or falls outside that range raises, so a typo
    never turns into an unbounded wait or a silent fallback.
    """
    raw = os.environ.get("EVAL_HTTP_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_HTTP_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError(f"EVAL_HTTP_TIMEOUT_SECONDS must be a number, got {raw!r}") from None
    if not 0 < value <= MAX_HTTP_TIMEOUT_SECONDS:
        raise RuntimeError(
            f"EVAL_HTTP_TIMEOUT_SECONDS must be in (0, {MAX_HTTP_TIMEOUT_SECONDS:g}], got {raw}"
        )
    return value
