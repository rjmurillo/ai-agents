"""Anthropic API adapter for eval-agent-vs-baseline.

DESIGN-004 §5.4 (AnthropicAPIAdapter). Thin wrapper over `_anthropic_api`
that adds retry policy, error categorization, and structured stderr logs.

Retry policy (REQ-004 AC-3, DESIGN-004 §Failure Modes):
- Transient (408, 429, 5xx, timeout) is retried only while the wall budget
  allows. When the next attempt plus its backoff would reach
  `total_timeout_seconds`, the call records `error_category=timeout_total`
  instead. Transient describes the error, not a promise of a second call.
- Non-transient 4xx (any other 4xx): record `outcome=error` immediately, no retry
- Max 3 attempts, exponential backoff with jitter (base=1s, max=30s). The wall
  budget can end a sequence after one attempt, so 3 is a ceiling, not a count.
- A status outranks a text hint when both are present, so a 4xx whose response
  body mentions a timeout stays non-transient.
- `temperature=0` is sent on every call, but not every transport honors it.
  Anthropic paths and non-reasoning OpenAI models apply it. Reasoning models
  (o-series and the gpt-5 family) reject a custom temperature, so `_providers`
  omits it, and Copilot CLI exposes no sampling controls, so it is discarded.
  A run on either is not temperature pinned, and the artifact records no
  provider to tell you which it was (issue #3956).

Logging:
- Structured JSON to stderr per call: `fixture_id`, `variant`, `model_id`,
  `attempt`, `outcome`, `latency_ms`, `tokens_in`, `tokens_out`, `error_category`
- Never logs API keys, request bodies, or full error payloads
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol, cast

# Sibling import; loaded under the same EVAL_DIR sys.path entry that the CLI uses.
import _eval_api_adapter_constants as _constants
from _anthropic_api import call_api, load_api_key

OutcomeLiteral = Literal["success", "error"]

ERR_RATE_LIMIT: str = _constants.ERR_RATE_LIMIT
ERR_SERVER_ERROR: str = _constants.ERR_SERVER_ERROR
ERR_TIMEOUT: str = _constants.ERR_TIMEOUT
ERR_CLIENT_ERROR: str = _constants.ERR_CLIENT_ERROR
ERR_AUTH: str = _constants.ERR_AUTH
ERR_UNKNOWN: str = _constants.ERR_UNKNOWN
ERR_TOTAL_TIMEOUT: str = _constants.ERR_TOTAL_TIMEOUT
DEFAULT_MAX_RETRIES: int = _constants.DEFAULT_MAX_RETRIES
DEFAULT_TOTAL_TIMEOUT_SEC: float = _constants.DEFAULT_TOTAL_TIMEOUT_SEC
_BACKOFF_BASE_SEC: float = _constants.BACKOFF_BASE_SEC
_BACKOFF_MAX_SEC: float = _constants.BACKOFF_MAX_SEC
_HTTP_STATUS_RE = _constants.HTTP_STATUS_RE
_TIMEOUT_HINT: str = _constants.TIMEOUT_HINT
_RATE_LIMIT_HINT: str = _constants.RATE_LIMIT_HINT
_AUTH_HINT_RE = _constants.AUTH_HINT_RE
_ALLOWED_LOG_FIELDS: frozenset[str] = _constants.ALLOWED_LOG_FIELDS
_BANNED_LOG_FIELDS: frozenset[str] = _constants.BANNED_LOG_FIELDS

# Re-exported so existing callers and tests reach them through this module.
_categorize_error = _constants.categorize_error
_is_transient = _constants.is_transient
_TRANSIENT: frozenset[str] = _constants.TRANSIENT


@dataclass(frozen=True)
class APICallResult:
    """Outcome of one (possibly-retried) API call. DESIGN-004 §5.4.

    `tokens_estimated` is True whenever counts did not come from a `usage`
    envelope: the success path's text-length heuristic, and the zeros an
    error path reports without counting. It drives a downstream cost caveat,
    so an absent measurement stays flagged instead of passing as a real zero.
    """

    outcome: OutcomeLiteral
    raw_response: str | None
    tokens_in: int
    tokens_out: int
    latency_ms: float
    error_category: str | None
    attempts: int
    tokens_estimated: bool = True
    system_fingerprint: str | None = None




def _backoff_delay_seconds(attempt: int) -> float:
    """Exponential backoff with full jitter. attempt is 1-based.

    base * 2^(attempt-1) capped at max, then uniform jitter in [0, capped].
    """
    cap = min(_BACKOFF_BASE_SEC * (2 ** (attempt - 1)), _BACKOFF_MAX_SEC)
    return random.uniform(0.0, cap)


def _emit_log(record: dict[str, object]) -> None:
    """Write a structured JSON log line to stderr.

    The closed field schema enforces DESIGN-004 §5.4. Unknown keys are refused
    before serialization so payload-shaped fields cannot enter stderr by
    caller convention drift.
    """
    unknown = record.keys() - _ALLOWED_LOG_FIELDS
    if unknown:
        banned = unknown & _BANNED_LOG_FIELDS
        detail = f"_emit_log rejected unknown keys: {sorted(unknown)}"
        if banned:
            detail += f" including banned fields: {sorted(banned)}"
        raise ValueError(detail)
    sys.stderr.write(json.dumps(record, sort_keys=True) + "\n")
    sys.stderr.flush()


# Type alias: an injectable transport. Tests pass a fake; production passes
# the wrapper around `_anthropic_api.call_api`. Keeping the seam at the
# constructor avoids monkey-patching.
Transport = Callable[[str, str, str], str]


class _ProviderWithFingerprint(Protocol):
    system_fingerprint: str | None

    def complete(self, **kwargs: object) -> str: ...


class _OpenAIProviderTransport:
    def __init__(self, provider: _ProviderWithFingerprint, *, seed: int | None) -> None:
        self._provider = provider
        self._seed = seed
        self.system_fingerprint: str | None = None

    def __call__(self, prompt: str, model_id: str, system: str) -> str:
        kwargs: dict[str, object] = {
            "messages": [{"role": "user", "content": prompt}],
            "system": system,
            "model": model_id,
            "max_tokens": 1024,
            "temperature": 0.0,
        }
        if self._seed is not None:
            kwargs["seed"] = self._seed
        text = self._provider.complete(**kwargs)
        fingerprint = getattr(self._provider, "system_fingerprint", None)
        if fingerprint is not None and not isinstance(fingerprint, str):
            raise RuntimeError(
                f"system_fingerprint must be str or None, got {type(fingerprint).__name__!r}"
            )
        self.system_fingerprint = fingerprint
        return text


class _AnthropicTransport:
    def __init__(self, api_key: str, *, seed: int | None) -> None:
        self._api_key = api_key
        self._seed = seed
        self.system_fingerprint: str | None = None

    def __call__(self, prompt: str, model_id: str, system: str) -> str:
        metadata: dict[str, object] = {}
        text = cast(
            str,
            call_api(
                api_key=self._api_key,
                messages=[{"role": "user", "content": prompt}],
                system=system,
                model=model_id,
                temperature=0.0,
                seed=self._seed,
                metadata=metadata,
            ),
        )
        fingerprint = metadata.get("system_fingerprint")
        if fingerprint is not None and not isinstance(fingerprint, str):
            raise RuntimeError(
                f"system_fingerprint must be str or None, got {type(fingerprint).__name__!r}"
            )
        self.system_fingerprint = fingerprint
        return text


def _default_transport_factory(seed: int | None = None) -> Transport:
    """Build the production transport selected by EVAL_PROVIDER.

    The default Anthropic urllib path reads ANTHROPIC_API_KEY once here and
    closes over it. Non-default providers load their own credentials inside
    their provider object, so this adapter never sees those secrets.
    """
    # Provider selection (EVAL_PROVIDER). A non-default provider self-loads
    # its own credential, so do not require ANTHROPIC_API_KEY via
    # load_api_key(). Baseline and variant run on the SAME provider per call
    # (ADR-058 symmetry); temperature=0 is pinned for reproducibility.
    provider = os.environ.get("EVAL_PROVIDER", "").strip()
    from _providers import is_default_anthropic, resolve_provider

    if provider and not is_default_anthropic(provider):
        selected_provider = resolve_provider(provider)
        return _OpenAIProviderTransport(selected_provider, seed=seed)

    api_key = load_api_key()
    return _AnthropicTransport(api_key, seed=seed)


class AnthropicAPIAdapter:
    """Adapter implementing retry + error categorization + redacted logs."""

    def __init__(
        self,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SEC,
        seed: int | None = None,
    ) -> None:
        # Lazy default: only resolve the API key when the adapter actually
        # needs the production transport. Tests inject `transport` directly.
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._total_timeout_seconds = total_timeout_seconds
        self._seed = seed

    def _resolve_transport(self) -> Transport:
        if self._transport is None:
            self._transport = _default_transport_factory(seed=self._seed)
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

        `max_retries` must be at least 1. A value of 0 or less is a caller
        mistake (no attempt would ever be made), not a retryable runtime
        condition.
        """
        if max_retries < 1:
            raise ValueError(
                f"max_retries must be at least 1, got {max_retries!r}. "
                "Pass max_retries=1 to make exactly one attempt with no retries."
            )
        resolve_start = self._clock()
        try:
            transport = self._resolve_transport()
        except Exception as exc:
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
                system_fingerprint=None,
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
                # This guard fires before the call, so `attempt` counts one
                # that never happened. Log the completed count so the stderr
                # stream and the returned `attempts` describe the same event.
                completed = attempt - 1
                _emit_log(
                    {
                        "fixture_id": fixture_id,
                        "variant": variant,
                        "run_index": run_index,
                        "model_id": model_id,
                        "attempt": completed,
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
                    attempts=completed,
                    tokens_estimated=True,
                    system_fingerprint=None,
                )
            attempt_start = self._clock()
            try:
                raw = transport(prompt, model_id, system)
            except Exception as exc:  # broad on purpose: categorize then decide
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
                        system_fingerprint=None,
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
                        system_fingerprint=None,
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
                system_fingerprint=getattr(transport, "system_fingerprint", None),
            )

        # Unreachable for positive `max_retries`; the loop returns on both exit
        # paths. Only `max_retries <= 0` lands here, having called nothing.
        total_latency_ms = (self._clock() - start_total) * 1000.0
        return APICallResult(
            outcome="error",
            raw_response=None,
            tokens_in=0,
            tokens_out=0,
            latency_ms=round(total_latency_ms, 2),
            error_category=last_category or ERR_UNKNOWN,
            attempts=attempt,
            system_fingerprint=None,
        )


def _estimate_tokens(text: str) -> int:
    """Token count approximation: ~4 chars per token. Used until the API
    helper surfaces real `usage` from the response envelope."""
    if not text:
        return 0
    return max(1, len(text) // 4)
