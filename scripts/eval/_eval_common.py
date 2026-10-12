"""Shared utilities for eval scripts.

Extracted from eval-agents.py and eval-knowledge-integration.py to eliminate
duplication of score aggregation logic.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from _billing_matrix import quota_billed_provider_names
from _eval_errors import MalformedProviderMetadataError

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EST_TOKENS_PER_CALL = 3500  # ~2000-5000 tokens per call, use midpoint
FLAKINESS_VARIANCE_THRESHOLD = 1.0

# Pricing rates per 1K tokens, USD. Owner of these constants for both
# _plan_runner.py (T4-1) and _report_aggregator.py (T4-3) per DESIGN-004 §5.3a.
# When updating, also update PRICING_RATE_AS_OF.
MODEL_PRICING_RATES_USD_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    # Legacy id retained for historical run cost lookups only; it is a dead
    # id (HTTP 404) and MUST NOT be used as a default (issue #2858).
    "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
    # Verified rates from platform.claude.com/docs/en/about-claude/pricing
    # (retrieved 2026-09-24, every row in this table re-read from that page on
    # that date). Rates are per-1K tokens = base MTok rate / 1000. Sonnet 4.6:
    # $3/$15 per MTok. Opus 5, 4.6, and 4.8: $5/$25 per MTok. Haiku 4.5:
    # $1/$5 per MTok. Sonnet 5: $2/$10 per MTok. Opus 5.5: $4/$20 per MTok.
    # Rows cover the live pins enumerated in issue #2840, claude-opus-5
    # (dispatched by scripts/eval/panels/owner-copilot-cli.json, unpriced
    # until issue #3905), the Sonnet 5 eval default, and Opus 5.5.
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    # Sonnet 5 is the eval default (issue #2858 single source).
    "claude-sonnet-5": {"input": 0.002, "output": 0.010},
    "claude-opus-4-6": {"input": 0.005, "output": 0.025},
    "claude-opus-4-8": {"input": 0.005, "output": 0.025},
    "claude-opus-5": {"input": 0.005, "output": 0.025},
    # Opus 5.5 in both harness spellings. The dotted id is the Copilot CLI
    # spelling that scripts/eval/panels/owner-copilot-cli.json dispatches.
    "claude-opus-5-5": {"input": 0.004, "output": 0.020},
    "claude-opus-5.5": {"input": 0.004, "output": 0.020},
    "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
    # GPT-6 rates from developers.openai.com/api/docs/models, re-read
    # 2026-09-24: Astra $10/$50, Sol $2/$10, Luna $0.10/$0.50 per MTok. These
    # ids are billed per token through the openai provider (OPENAI_API_KEY).
    # No GPT-5.6 row: that page publishes no GPT-5.6 rate to verify against.
    "gpt-6-astra": {"input": 0.010, "output": 0.050},
    "gpt-6-sol": {"input": 0.002, "output": 0.010},
    "gpt-6-luna": {"input": 0.0001, "output": 0.0005},
    # No row for gpt-5.6-sol on purpose (issue #3905). That id is reachable
    # only through the copilot-cli provider, which meters premium requests
    # rather than tokens, so no published per-token rate exists. A made-up
    # number here would put a fabricated figure in an operator cost report,
    # which is the failure issue #3786 records. Its cost basis is tracked in
    # PR #4005.
}
PRICING_RATE_AS_OF = "2026-09-24"

# Providers that meter requests against an account allowance instead of
# charging a published per-token USD rate. Every subscription cell bills this
# way: it shells out to a CLI covered by a seat the operator already pays for,
# so it spends no per-token dollars at all. Naming these providers lets the
# plan report the request count it will spend and leave the USD figure empty,
# rather than either inventing a third-party price or refusing to run a
# provider the transport already supports.
#
# The set is derived from `_billing_matrix`, not restated here, so the biller
# a run is charged on and the transport it runs on cannot drift apart. Adding
# a registry row without a matrix cell leaves it unclassified, and
# `TestEveryRegisteredProviderIsClassified` fails, because the default is
# silent and the omission of `copilot-cli` from this set is what once made a
# subscription CLI quote a Claude Sonnet token rate.

# Retired GitHub Models rows. They predate the billing matrix and are not in
# it, because the matrix describes cells an operator should select and these
# route to an endpoint that has returned HTTP 410 since 2026-07-30. They stay
# classified here so a historical run artifact still reads back with the basis
# it was charged on.
_RETIRED_QUOTA_BILLED: frozenset[str] = frozenset({"github", "github-models"})

QUOTA_BILLED_PROVIDERS: frozenset[str] = quota_billed_provider_names() | _RETIRED_QUOTA_BILLED


# Anthropic deprecates `temperature` per model, not all at once: as of
# 2026-09-22, claude-sonnet-5, claude-opus-4-8, claude-opus-5-5, and
# claude-fable-5-1 reject it with this HTTP 400 message; claude-opus-4-6,
# claude-sonnet-4-6, claude-sonnet-4-5, and claude-haiku-4-5-20251001 still
# accept it. Matching the documented message instead of hand-keeping a model
# list means a newly deprecated model needs no code change here: the next
# `call_with_temperature_fallback` call just retries once without the field.
#
# Live-verified 2026-09-23 against claude-sonnet-5: the API's actual wording
# quotes the field with backticks (`` `temperature` is deprecated for this
# model. ``), not double quotes as a first written description of this
# message assumed. `[`"']?\\?` on both sides tolerates a backtick, a bare
# quote (a Python-side exception message, e.g. the SDK's
# `BadRequestError.message`, already JSON-decoded), or a backslash-escaped
# quote (the raw, undecoded HTTP response body the urllib transport matches
# against before it parses JSON).
_TEMPERATURE_DEPRECATED_RE = re.compile(
    r"[`\"']?\\?temperature\\?[`\"']?\s+is\s+deprecated\s+for\s+this\s+model",
    re.IGNORECASE,
)


def is_temperature_deprecated_message(message: str) -> bool:
    """True when a 400 body says the model has deprecated `temperature`."""
    return bool(_TEMPERATURE_DEPRECATED_RE.search(message))


def call_with_temperature_fallback(
    send: Callable[[bool], _T],
    is_deprecated_error: Callable[[Exception], bool],
) -> _T:
    """Call `send(True)`; on a temperature-deprecated 400, retry `send(False)`.

    `send` takes one bool: whether this attempt should include `temperature`
    in the request. `is_deprecated_error` inspects the raised exception
    (before any redaction) for the documented 400 shape. One shared retry
    policy for both Anthropic transports (SDK and urllib) instead of two
    copies of the same decision; each transport supplies its own `send` and
    its own way of reading the exception the underlying client raises.
    """
    try:
        return send(True)
    except Exception as exc:
        if not is_deprecated_error(exc):
            raise
        return send(False)


# Closed set of provider `error.type` values that may be echoed. The Anthropic
# API documents these; the OpenAI-compatible providers reuse `invalid_request_error`
# and `authentication_error`. Anything outside the set is dropped, never echoed,
# because a provider-controlled string must not reach logs or persisted artifacts.
PROVIDER_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "invalid_request_error",
        "authentication_error",
        "billing_error",
        "permission_error",
        "not_found_error",
        "request_too_large",
        "rate_limit_error",
        "timeout_error",
        "api_error",
        "overloaded_error",
    }
)

# The fixed phrase the Anthropic API returns when the credit balance is depleted
# (HTTP 400, error.type=invalid_request_error). Matched, never echoed.
_CREDIT_BALANCE_RE = re.compile(r"credit\s+balance\s+(?:is\s+)?too\s+low", re.IGNORECASE)

# Token that marks a billing failure in a `safe_http_error_message` result, so a
# caller can tell "fund the key" from "fix the request" without a second parse.
BILLING_ERROR_MARKER = "error=billing"

_MAX_BODY_CHARS = 65536


def _error_object(parsed: object) -> dict[str, Any]:
    """Return the dict holding `type` and `message` from a parsed provider body.

    Anthropic wraps it as ``{"type": "error", "error": {...}}``. The OpenAI SDK
    hands back the inner object directly. Anything else yields an empty dict.
    """
    if not isinstance(parsed, dict):
        return {}
    inner = parsed.get("error")
    return inner if isinstance(inner, dict) else parsed


def _decode_body(body: object) -> object:
    """Turn raw bytes or text into a parsed JSON value, or the raw text when it is not JSON."""
    if isinstance(body, bytes):
        body = body.decode(errors="replace")
    if not isinstance(body, str):
        return body
    text = body[:_MAX_BODY_CHARS]
    try:
        return json.loads(text)
    except ValueError:
        return text


def classify_provider_error_body(body: object) -> tuple[str | None, bool]:
    """Return ``(error_type, is_credit_balance)`` read from a provider error body.

    *body* may be bytes, text, an already-parsed dict (SDK exceptions), or None.
    ``error_type`` is the provider's ``error.type`` only when it is in
    ``PROVIDER_ERROR_TYPES``; otherwise None. ``is_credit_balance`` is True when
    the error message carries the fixed depleted-credit phrase. No part of the
    body text is returned, so the redaction policy holds.
    """
    parsed = _decode_body(body)
    if isinstance(parsed, str):
        return None, bool(_CREDIT_BALANCE_RE.search(parsed))
    error = _error_object(parsed)
    raw_type = error.get("type")
    error_type = (
        raw_type if isinstance(raw_type, str) and raw_type in PROVIDER_ERROR_TYPES else None
    )
    message = error.get("message")
    return error_type, isinstance(message, str) and bool(_CREDIT_BALANCE_RE.search(message))


def _http_category(status_code: int, error_type: str | None, credit_balance: bool) -> str:
    if error_type == "billing_error" or (status_code == 400 and credit_balance):
        return "billing"
    if status_code in (401, 403):
        return "auth"
    if status_code == 408:
        return "timeout"
    if status_code == 429:
        return "rate_limit"
    if 500 <= status_code < 600:
        return "server_error"
    if 400 <= status_code < 500:
        return "client_error"
    return "http_error"


def is_billing_error_message(message: str) -> bool:
    """True when *message* came from `safe_http_error_message` as a billing failure."""
    return BILLING_ERROR_MARKER in message and "returned HTTP" in message


def safe_http_error_message(
    provider_surface: str,
    status_code: int,
    body: object = None,
) -> str:
    """Return a fixed HTTP error that contains no provider-controlled body text.

    *body* is optional. When given, only two facts are read from it: the
    provider's `error.type`, appended when it is in `PROVIDER_ERROR_TYPES`, and
    whether the message says the credit balance is too low, which reports
    ``error=billing``. The body text itself is never returned.
    """
    error_type, credit_balance = classify_provider_error_body(body)
    category = _http_category(status_code, error_type, credit_balance)
    type_part = f"provider_error_type={error_type}; " if error_type else ""
    return (
        f"{provider_surface} returned HTTP {status_code}: error={category}; "
        f"{type_part}provider response redacted"
    )


def cost_basis(provider: str | None) -> str:
    """Return how *provider* bills: ``"usd"`` per token or ``"requests"``.

    The biller is the provider, not the model. The same model id served
    through GitHub Models is metered against a request allowance, and served
    through a per-token vendor is metered in dollars, so the basis has to
    follow the transport that will actually be charged.

    *provider* is resolved exactly as ``_providers.resolve_provider`` resolves
    it, ``(name or EVAL_PROVIDER or "anthropic").strip().lower()``, because the
    transport that resolution selects is the one that gets billed. Resolving
    any other way lets the two disagree: selecting GitHub Models through the
    environment alone, or spelling it ``GitHub-Models``, would route to a
    request-metered transport while this function still answered ``"usd"``,
    so the plan would promise dollars for a run that spends request quota.

    An unrecognized or absent provider answers ``"usd"``. That keeps the
    default Anthropic path, and any per-token vendor added later, on the
    existing rule: a missing rate is a real gap an operator must fill, not a
    licence to print a price.
    """
    selected = (provider or os.environ.get("EVAL_PROVIDER") or "anthropic").strip().lower()
    return "requests" if selected in QUOTA_BILLED_PROVIDERS else "usd"


def percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interpolation percentile of `values` at `pct` (0 to 100). No numpy.

    Returns 0.0 for an empty sequence and the sole value for a single-element
    sequence. This is the one merged copy (REQ-042 AC-11) of the two
    formerly-private ``_percentile`` helpers in ``_model_sweep_core.py`` and
    ``_report_aggregator.py``; both call sites now import this function
    instead of keeping their own copy.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    frac = rank - lower
    return ordered[lower] + frac * (ordered[upper] - ordered[lower])


def require_str_or_none(value: object, field: str) -> str | None:
    """Return `value` when it is a string or absent; raise when it is neither.

    This is the shared write policy for object-typed provider provenance.

    Coercing a malformed value to `None` instead records "the provider
    supplied nothing" for a value the provider did supply.

    Canonical reader contract, verbatim from
    `scripts/eval/_run_persistence.py::_validate_payload`:
        f"{line_context} field 'system_fingerprint' has wrong type "
        f"(expected str or null, got {type(fingerprint).__name__})"

    Different than canonical: this helper raises
    `MalformedProviderMetadataError` at the provider boundary. The canonical
    reader raises `MalformedRunRecordError` while decoding an archive. Both
    accept only a string or null for this field (issue #4123).
    """
    if value is None or isinstance(value, str):
        return value
    raise MalformedProviderMetadataError(
        f"provider returned a non-string {field} ({type(value).__name__})"
    )


def aggregate_multi_run_scores(
    run_scores: list[dict[str, Any]],
    dimensions: list[str],
) -> dict[str, Any]:
    """Aggregate scores across multiple runs per ADR-057 flakiness protocol.

    Returns averaged scores plus flakiness metadata (pass rate, variance).

    Args:
        run_scores: List of score dicts from individual runs.
        dimensions: List of dimension keys to aggregate (e.g. ["accuracy", "depth", "specificity"]).
    """
    if len(run_scores) == 1:
        return run_scores[0]

    aggregated: dict[str, Any] = {}
    for dim in dimensions:
        values = [s[dim] for s in run_scores if dim in s and s[dim] is not None]
        if values:
            aggregated[dim] = round(sum(values) / len(values), 2)
            aggregated[f"{dim}_variance"] = round(
                sum((v - aggregated[dim]) ** 2 for v in values) / len(values), 2
            )
        else:
            aggregated[dim] = 0.0

    # Flakiness detection: a scenario is flaky if any dimension varies by > threshold
    max_variance = max((aggregated.get(f"{d}_variance", 0) for d in dimensions), default=0)
    aggregated["runs"] = len(run_scores)
    aggregated["flaky"] = max_variance > FLAKINESS_VARIANCE_THRESHOLD
    aggregated["max_variance"] = round(max_variance, 2)

    # Preserve non-score fields from first run
    preserved_keys = ("complexity", "model_used", "reasoning")
    for key in preserved_keys:
        if key in run_scores[0]:
            aggregated[key] = run_scores[0][key]

    if len(run_scores) > 1:
        aggregated["per_run_detail"] = run_scores
    return aggregated
