"""Anthropic API adapter for eval-agent-vs-baseline.

DESIGN-004 §5.4 (AnthropicAPIAdapter). Thin wrapper over `_anthropic_api`
that adds retry policy, error categorization, and structured stderr logs.

Retry policy (REQ-004 AC-3, DESIGN-004 §Failure Modes):
- Transient categories (retried): 408, 429, 5xx, timeout
- Non-transient 4xx (any other 4xx): record `outcome=error` immediately, no retry
- Max 3 attempts, exponential backoff with jitter (base=1s, max=30s)
- `temperature=0` enforced on every call

Logging:
- Structured JSON to stderr per call: `fixture_id`, `variant`, `model_id`,
  `attempt`, `outcome`, `latency_ms`, `tokens_in`, `tokens_out`, `error_category`
- Never logs API keys, request bodies, or full error payloads
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

# Sibling import; loaded under the same EVAL_DIR sys.path entry that the CLI uses.
from _anthropic_api import call_api, load_api_key

OutcomeLiteral = Literal["success", "error"]

# Error category taxonomy. Stable strings written into RunRecord.error_category.
ERR_RATE_LIMIT = "rate_limit"
ERR_SERVER_ERROR = "server_error"
ERR_TIMEOUT = "timeout"
ERR_CLIENT_ERROR = "client_error"
ERR_AUTH = "auth"
ERR_UNKNOWN = "unknown"

# Bounded retry policy.
DEFAULT_MAX_RETRIES = 3
_BACKOFF_BASE_SEC = 1.0
_BACKOFF_MAX_SEC = 30.0

# Total wall-time budget across all attempts for one logical call.
# `_anthropic_api.call_api` uses a 120s per-attempt timeout; with 3 retries
# the worst case before this guard was 6 minutes per call. 180s caps the
# guarantee at one slow attempt without forfeiting fast retries.
DEFAULT_TOTAL_TIMEOUT_SEC = 180.0
ERR_TOTAL_TIMEOUT = "timeout_total"


@dataclass(frozen=True)
class APICallResult:
    """Outcome of one (possibly-retried) API call. DESIGN-004 §5.4.

    `tokens_estimated` is True when token counts are derived from a
    text-length heuristic instead of a `usage` envelope returned by the
    API. The eval pipeline propagates this flag into `runs.jsonl` and the
    aggregated report so cost numbers are not presented as authoritative.
    """

    outcome: OutcomeLiteral
    raw_response: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: float
    error_category: str | None
    attempts: int
    tokens_estimated: bool = True


# Match the HTTP-status hint that `_anthropic_api.call_api` puts into its
# RuntimeError message: "Anthropic API returned HTTP <code>: ...". Capture
# the numeric code so the adapter can categorize without re-implementing the
# request loop.
_HTTP_STATUS_RE = re.compile(r"HTTP (\d{3})")
_TIMEOUT_HINT = "timed out"


def _categorize_error(exc: Exception) -> str:
    """Translate a `_anthropic_api.call_api` RuntimeError into an error_category.

    The underlying API helper raises `RuntimeError` with one of three
    well-known message shapes (see `_anthropic_api.py`): HTTP error,
    timeout, or other URLError. Anything else falls through to `unknown`.
    """
    message = str(exc)
    if _TIMEOUT_HINT in message:
        return ERR_TIMEOUT
    match = _HTTP_STATUS_RE.search(message)
    if match is None:
        # No HTTP status code → treat as transient network issue.
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
    return ERR_UNKNOWN


# Retried = transient. Anything else is recorded once and not retried.
_TRANSIENT = frozenset({ERR_RATE_LIMIT, ERR_SERVER_ERROR, ERR_TIMEOUT})


def _is_transient(category: str) -> bool:
    return category in _TRANSIENT


def _backoff_delay_seconds(attempt: int) -> float:
    """Exponential backoff with full jitter. attempt is 1-based.

    base * 2^(attempt-1) capped at max, then uniform jitter in [0, capped].
    """
    cap = min(_BACKOFF_BASE_SEC * (2 ** (attempt - 1)), _BACKOFF_MAX_SEC)
    return random.uniform(0.0, cap)


def _emit_log(record: dict[str, object]) -> None:
    """Write a structured JSON log line to stderr.

    Caller MUST NOT include API keys, request bodies, or raw error payloads.
    Only the fields listed in DESIGN-004 §5.4 belong here.
    """
    sys.stderr.write(json.dumps(record, sort_keys=True) + "\n")
    sys.stderr.flush()


# Type alias: an injectable transport. Tests pass a fake; production passes
# the wrapper around `_anthropic_api.call_api`. Keeping the seam at the
# constructor avoids monkey-patching.
Transport = Callable[[str, str, str], str]


def _default_transport_factory() -> Transport:
    """Build the production transport. Reads the API key once, here, and
    closes over it so callers never see the secret."""
    # Provider selection (EVAL_PROVIDER). A non-default provider self-loads
    # its own credential, so do not require ANTHROPIC_API_KEY via
    # load_api_key(). Baseline and variant run on the SAME provider per call
    # (ADR-058 symmetry); temperature=0 is pinned for reproducibility.
    provider = os.environ.get("EVAL_PROVIDER", "").strip()
    from _providers import is_default_anthropic, resolve_provider

    if provider and not is_default_anthropic(provider):
        resolve_provider(provider)

        def _call_provider(prompt: str, model_id: str, system: str) -> str:
            return call_api(
                api_key="",
                messages=[{"role": "user", "content": prompt}],
                system=system,
                model=model_id,
                temperature=0.0,
                provider=provider,
            )

        return _call_provider

    api_key = load_api_key()

    def _call(prompt: str, model_id: str, system: str) -> str:
        # Determinism is contractual for this adapter (REQ-004 AC-3 /
        # ADR-058 §"Experimental Design Symmetry"). Pass temperature=0
        # explicitly here rather than relying on `call_api`'s default so
        # a future helper change cannot silently break reproducibility.
        return call_api(
            api_key=api_key,
            messages=[{"role": "user", "content": prompt}],
            system=system,
            model=model_id,
            temperature=0.0,
        )

    return _call


class AnthropicAPIAdapter:
    """Adapter implementing retry + error categorization + redacted logs."""

    def __init__(
        self,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SEC,
    ) -> None:
        # Lazy default: only resolve the API key when the adapter actually
        # needs the production transport. Tests inject `transport` directly.
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._total_timeout_seconds = total_timeout_seconds

    def _resolve_transport(self) -> Transport:
        if self._transport is None:
            self._transport = _default_transport_factory()
        return self._transport

    def call_model(
        self,
        prompt: str,
        model_id: str,
        fixture_id: str,
        variant: str,
        run_index: int,
        *,
        system: str = "",
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> APICallResult:
        """Issue one API call (with up to `max_retries` retries on transient errors).

        Returns `APICallResult` regardless of outcome, including the case
        where transport construction itself fails (for example, no
        `ANTHROPIC_API_KEY` available to `_default_transport_factory`).
        Construction failure is categorized as `auth` since the production
        transport's only resolve-time dependency is `load_api_key()`.
        Never raises on transport failure; the caller inspects `outcome`
        and `error_category`. Logs one structured line per attempt to
        stderr.
        """
        resolve_start = self._clock()
        try:
            transport = self._resolve_transport()
        except Exception as exc:  # noqa: BLE001 - categorize-then-decide
            latency_ms = (self._clock() - resolve_start) * 1000.0
            # Best-effort categorization: today the only resolve-time
            # raise is `load_api_key()` raising RuntimeError when no key
            # is configured (or the CWE-22 symlink defense fires). Both
            # are auth-class. Reuse the HTTP-status-aware classifier for
            # any future resolve-time error that happens to carry an
            # HTTP code in its message.
            category = _categorize_error(exc)
            if category in (ERR_SERVER_ERROR, ERR_UNKNOWN):
                # No HTTP signal: the failure is at config-resolution
                # time, which the contract above pins as `auth`.
                category = ERR_AUTH
            _emit_log(
                {
                    "fixture_id": fixture_id,
                    "variant": variant,
                    "run_index": run_index,
                    "model_id": model_id,
                    "attempt": 0,
                    "outcome": "error",
                    "latency_ms": round(latency_ms, 2),
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "error_category": category,
                }
            )
            return APICallResult(
                outcome="error",
                raw_response=None,
                tokens_in=0,
                tokens_out=0,
                latency_ms=round(latency_ms, 2),
                error_category=category,
                attempts=0,
                tokens_estimated=True,
            )
        attempt = 0
        last_category: str | None = None
        start_total = self._clock()

        while attempt < max_retries:
            attempt += 1
            # Wall-budget guard: if elapsed already exceeds the total budget,
            # do not start another attempt. Logged once and returned as a
            # `timeout_total` error so the operator can distinguish it from
            # per-attempt timeouts.
            elapsed = self._clock() - start_total
            if attempt > 1 and elapsed >= self._total_timeout_seconds:
                _emit_log(
                    {
                        "fixture_id": fixture_id,
                        "variant": variant,
                        "run_index": run_index,
                        "model_id": model_id,
                        "attempt": attempt,
                        "outcome": "error",
                        "latency_ms": round(elapsed * 1000.0, 2),
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "error_category": ERR_TOTAL_TIMEOUT,
                    }
                )
                return APICallResult(
                    outcome="error",
                    raw_response=None,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=round(elapsed * 1000.0, 2),
                    error_category=ERR_TOTAL_TIMEOUT,
                    attempts=attempt - 1,
                    tokens_estimated=True,
                )
            attempt_start = self._clock()
            try:
                raw = transport(prompt, model_id, system)
            except Exception as exc:  # broad on purpose — categorize then decide
                category = _categorize_error(exc)
                last_category = category
                latency_ms = (self._clock() - attempt_start) * 1000.0
                _emit_log(
                    {
                        "fixture_id": fixture_id,
                        "variant": variant,
                        "run_index": run_index,
                        "model_id": model_id,
                        "attempt": attempt,
                        "outcome": "error",
                        "latency_ms": round(latency_ms, 2),
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "error_category": category,
                    }
                )
                if not _is_transient(category) or attempt >= max_retries:
                    total_latency_ms = (self._clock() - start_total) * 1000.0
                    return APICallResult(
                        outcome="error",
                        raw_response=None,
                        tokens_in=0,
                        tokens_out=0,
                        latency_ms=round(total_latency_ms, 2),
                        error_category=category,
                        attempts=attempt,
                        tokens_estimated=True,
                    )
                # Transient + budget remaining → backoff and retry, but only
                # if the next attempt + its backoff fits inside the wall
                # budget. Otherwise abort with `timeout_total`.
                backoff = _backoff_delay_seconds(attempt)
                projected = (self._clock() - start_total) + backoff
                if projected >= self._total_timeout_seconds:
                    total_latency_ms = (self._clock() - start_total) * 1000.0
                    _emit_log(
                        {
                            "fixture_id": fixture_id,
                            "variant": variant,
                            "run_index": run_index,
                            "model_id": model_id,
                            "attempt": attempt,
                            "outcome": "error",
                            "latency_ms": round(total_latency_ms, 2),
                            "tokens_in": 0,
                            "tokens_out": 0,
                            "error_category": ERR_TOTAL_TIMEOUT,
                        }
                    )
                    return APICallResult(
                        outcome="error",
                        raw_response=None,
                        tokens_in=0,
                        tokens_out=0,
                        latency_ms=round(total_latency_ms, 2),
                        error_category=ERR_TOTAL_TIMEOUT,
                        attempts=attempt,
                        tokens_estimated=True,
                    )
                self._sleep(backoff)
                continue

            # Success path. Token counts are estimated from text length until
            # `_anthropic_api.call_api` surfaces a `usage` envelope; callers
            # see `tokens_estimated=True` so cost numbers carry that caveat.
            latency_ms = (self._clock() - attempt_start) * 1000.0
            total_latency_ms = (self._clock() - start_total) * 1000.0
            tokens_in = _estimate_tokens(prompt) + _estimate_tokens(system)
            tokens_out = _estimate_tokens(raw)
            _emit_log(
                {
                    "fixture_id": fixture_id,
                    "variant": variant,
                    "run_index": run_index,
                    "model_id": model_id,
                    "attempt": attempt,
                    "outcome": "success",
                    "latency_ms": round(latency_ms, 2),
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "error_category": None,
                }
            )
            return APICallResult(
                outcome="success",
                raw_response=raw,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round(total_latency_ms, 2),
                error_category=None,
                attempts=attempt,
                tokens_estimated=True,
            )

        # Exhausted retries on transient error without ever getting an
        # exception inside the loop — defensive fallthrough; should not occur.
        total_latency_ms = (self._clock() - start_total) * 1000.0
        return APICallResult(
            outcome="error",
            raw_response=None,
            tokens_in=0,
            tokens_out=0,
            latency_ms=round(total_latency_ms, 2),
            error_category=last_category or ERR_UNKNOWN,
            attempts=attempt,
        )


def _estimate_tokens(text: str) -> int:
    """Token count approximation: ~4 chars per token. Used until the API
    helper surfaces real `usage` from the response envelope."""
    if not text:
        return 0
    return max(1, len(text) // 4)
