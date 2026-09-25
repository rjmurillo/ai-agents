"""Shared Anthropic API utilities for evaluation scripts.

This module provides common functions for loading API keys, calling the
Anthropic Messages API, and loading custom prompt JSON files. Used by
eval-agents.py and eval-knowledge-integration.py.

`call_api_response` (REQ-037) returns a structured `MessageResponse` that
keeps the response's `stop_reason` and classifies it into a `Termination`
category, so a caller can tell a refusal or a token-limit cutoff from a
completed answer. `call_api` stays a text-only view over the same call for
the existing callers that read a string; it writes `termination` and
`stop_reason` into an optional `metadata` dict rather than changing its
return type.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

# Sibling import; loaded under the same EVAL_DIR sys.path entry every caller
# of this module already uses to reach it by bare name.
from _eval_common import (
    call_with_temperature_fallback,
    is_temperature_deprecated_message,
    require_str_or_none,
    safe_http_error_message,
)
from _eval_errors import TemperatureDeprecatedError

# Single source of truth for the default eval model. Every eval script imports
# this instead of hard-coding an id, so a model bump is a one-line change here
# (issue #2858). The previous default `claude-sonnet-4-20250514` is a dead id
# that returns HTTP 404 against a current key. `claude-sonnet-5` follows the
# routing policy in AGENTS.md (Sonnet 5 for specified judgment) and is priced
# in `_eval_common.py`. It rejects `temperature`; `call_api` retries without it.
DEFAULT_MODEL = "claude-sonnet-5"

_MODELS_ENDPOINT = "https://api.anthropic.com/v1/models"

# REQ-037 termination map. A Messages API `stop_reason` classifies into one
# of five buckets; new provider stop reasons degrade to `incomplete` rather
# than being scored as a completed answer (REQ-037 Q6/Failure Modes).
Termination = Literal["completed", "refusal", "token_limit", "incomplete", "unknown"]

_COMPLETED_STOP_REASONS: frozenset[str] = frozenset({"end_turn", "stop_sequence"})
_REFUSAL_STOP_REASON = "refusal"
_TOKEN_LIMIT_STOP_REASONS: frozenset[str] = frozenset(
    {"max_tokens", "model_context_window_exceeded"}
)

# REQ-037 Failure Modes: a refusal, a token-limit cutoff, and an unrecognized
# stop reason (`incomplete`) must never be scored as an answer. The single
# source of truth for that gate; every caller (the adapter and the two
# evaluators) checks membership here instead of repeating the tuple.
NON_SCOREABLE_TERMINATIONS: frozenset[str] = frozenset({"refusal", "token_limit", "incomplete"})


def classify_termination(stop_reason: object) -> Termination:
    """Map a raw `stop_reason` value to a `Termination` category.

    REQ-037 termination map (DESIGN-035):

    | `stop_reason`                                   | Termination   |
    |--------------------------------------------------|---------------|
    | `end_turn`, `stop_sequence`                       | `completed`   |
    | `refusal`                                         | `refusal`     |
    | `max_tokens`, `model_context_window_exceeded`     | `token_limit` |
    | any other string                                  | `incomplete`  |
    | missing or not a string                           | `unknown`     |
    """
    if not isinstance(stop_reason, str):
        return "unknown"
    if stop_reason in _COMPLETED_STOP_REASONS:
        return "completed"
    if stop_reason == _REFUSAL_STOP_REASON:
        return "refusal"
    if stop_reason in _TOKEN_LIMIT_STOP_REASONS:
        return "token_limit"
    return "incomplete"


@dataclass(frozen=True, slots=True)
class MessageResponse:
    """Structured result of one Messages API call (REQ-037 Data Model).

    Created once per call by `parse_message_response` and never mutated.
    `block_types` preserves content-block order as returned by the API;
    `text` joins only the `text` blocks with `\\n`, matching the historical
    `call_api` return value byte-for-byte.
    """

    text: str
    stop_reason: str | None
    termination: Termination
    block_types: tuple[str, ...]
    refusal_category: str | None = None
    refusal_explanation: str | None = None

    @property
    def blocks_scoring(self) -> bool:
        """True when this response must not be scored as an answer.

        REQ-037 AC-9/Failure Modes: a refusal, a token-limit cutoff, or an
        unrecognized stop reason is recorded, never scored as a right or
        wrong verdict.
        """
        return self.termination in NON_SCOREABLE_TERMINATIONS


def parse_message_response(payload: dict[str, Any]) -> MessageResponse:
    """Parse a Messages API response body into a `MessageResponse`.

    Reads the response dict once. Non-dict content blocks and blocks with a
    missing or non-string `type` are skipped when building `block_types`
    (defensive; the live API always sends dict blocks with a string `type`).
    Refusal `category`/`explanation` are read from `stop_details` only when
    `stop_reason == "refusal"` and `stop_details` is itself a dict; a
    non-string category or explanation is dropped rather than propagated.
    """
    content = payload.get("content", [])
    block_types: list[str] = []
    text_parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if not isinstance(block_type, str):
                continue
            block_types.append(block_type)
            text = block.get("text")
            if block_type == "text" and isinstance(text, str):
                text_parts.append(text)

    stop_reason_raw = payload.get("stop_reason")
    stop_reason = stop_reason_raw if isinstance(stop_reason_raw, str) else None
    termination = classify_termination(stop_reason_raw)

    refusal_category: str | None = None
    refusal_explanation: str | None = None
    if stop_reason == _REFUSAL_STOP_REASON:
        stop_details = payload.get("stop_details")
        if isinstance(stop_details, dict):
            category = stop_details.get("category")
            if isinstance(category, str):
                refusal_category = category
            explanation = stop_details.get("explanation")
            if isinstance(explanation, str):
                refusal_explanation = explanation

    return MessageResponse(
        text="\n".join(text_parts),
        stop_reason=stop_reason,
        termination=termination,
        block_types=tuple(block_types),
        refusal_category=refusal_category,
        refusal_explanation=refusal_explanation,
    )


def load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from environment or .env file.

    Searches for the key in:
    1. ANTHROPIC_API_KEY environment variable
    2. .env file in the script's directory or parent directories (up to 10 levels)

    Returns:
        The API key string.

    Raises:
        RuntimeError: If the key is not found in the environment or any .env file.
            Callers at the CLI boundary should catch this and sys.exit(1) if
            process termination is appropriate.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()

    # CWE-22 mitigation: only consult `.env` files inside the repository
    # root, never walk up arbitrary parent directories. An attacker that
    # plants a `.env` higher in the filesystem MUST NOT be able to feed
    # the runner credentials. `parents[2]` is the repo root for this
    # script's canonical layout (`scripts/eval/_anthropic_api.py`); a
    # symlink to `__file__` would relocate `parents[2]`, so reject those
    # too. The check MUST run before `resolve()` because `resolve()`
    # dereferences the symlink and would mask the attacker-controlled path.
    raw = Path(__file__)
    if raw.is_symlink():
        raise RuntimeError(
            "ANTHROPIC_API_KEY load aborted: refusing to resolve symlinked "
            "module path (CWE-22 defense)."
        )
    here = raw.resolve(strict=True)
    repo_root = here.parents[2]
    candidates = [repo_root / ".env"]
    for env_path in candidates:
        if env_path.is_symlink() or not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "ANTHROPIC_API_KEY":
                value = v.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                return value

    raise RuntimeError(
        "ANTHROPIC_API_KEY not found in environment or repo-root .env file. "
        "Set the environment variable or add it to .env at the repo root."
    )


def load_api_key_for_selected_provider(provider: str | None = None) -> str:
    """Load the Anthropic key, or return "" when another transport is selected.

    Every eval entry point wants a credential precondition so a long run does
    not die on call one. Only the default urllib path needs *this* credential
    though: a non-default provider loads its own inside its provider object,
    and `copilot-cli` has none at all. Entry points that call `load_api_key()`
    unconditionally make `EVAL_PROVIDER` unreachable from the command line even
    though `call_api` honors it, which is how the harness ended up unable to
    run against the models this repository is actually operated in.

    Mirrors the no-op condition `verify_model_available` already applies, so
    the preflight pair agrees on which transport is in play.
    """
    from _providers import is_default_anthropic

    selected = provider if provider is not None else os.environ.get("EVAL_PROVIDER")
    if not is_default_anthropic(selected):
        return ""
    return load_api_key()


def _call_selected_provider(
    selected: str | None,
    messages: list[dict[str, str]],
    system: str,
    model: str,
    max_tokens: int,
    temperature: float | None,
    seed: int | None,
    metadata: dict[str, object] | None,
) -> str | None:
    if selected is None:
        return None
    from _providers import is_default_anthropic, resolve_provider

    if is_default_anthropic(selected):
        return None
    selected_provider = resolve_provider(selected)
    kwargs: dict[str, object] = {
        "messages": messages,
        "system": system,
        "model": model,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if seed is not None:
        kwargs["seed"] = seed
    text = cast(str, selected_provider.complete(**kwargs))
    fingerprint = require_str_or_none(
        getattr(selected_provider, "system_fingerprint", None),
        "system_fingerprint",
    )
    if metadata is not None and fingerprint is not None:
        metadata["system_fingerprint"] = fingerprint
    return text


def _build_messages_request(
    api_key: str,
    messages: list[dict[str, str]],
    system: str,
    model: str,
    max_tokens: int,
    temperature: float | None,
) -> urllib.request.Request:
    """Build the `POST /v1/messages` request. `temperature=None` omits the
    field entirely, for the retry after the model rejects it as deprecated.
    """
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if temperature is not None:
        body["temperature"] = temperature
    if system:
        body["system"] = system
    return urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )


def _reachable_model_hint(api_key: str) -> str:
    try:
        list_available_models(api_key)
    except Exception:
        print(
            "warning: reachable-model lookup failed: provider details redacted",
            file=sys.stderr,
        )
        return ""
    return (
        ". Requested model is unavailable; query the models endpoint "
        "for reachable model IDs"
    )


def _read_messages_response(
    request: urllib.request.Request,
    api_key: str,
) -> object:
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode(errors="replace"))
    except urllib.error.HTTPError as error:
        if error.code == 400:
            # Inspect the raw body before it is redacted below. Discarded
            # immediately if it doesn't match; never logged or re-raised.
            detail = error.read().decode(errors="replace")
            if is_temperature_deprecated_message(detail):
                raise TemperatureDeprecatedError from None
        message = safe_http_error_message("Anthropic API", error.code)
        if error.code == 404:
            message += _reachable_model_hint(api_key)
        raise RuntimeError(message) from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise RuntimeError(
                "Anthropic API request timed out after 120s. "
                "The service may be slow or unreachable."
            ) from None
        raise RuntimeError(
            "Anthropic API network error: error=network_failure; provider details redacted"
        ) from None
    except TimeoutError:
        raise RuntimeError(
            "Anthropic API request timed out after 120s. The service may be slow or unreachable."
        ) from None
    except json.JSONDecodeError:
        raise RuntimeError(
            "Anthropic API returned invalid JSON: error=invalid_json; provider response redacted"
        ) from None


def call_api_response(
    api_key: str,
    messages: list[dict[str, str]],
    system: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
    temperature: float | None = 0.0,
    provider: str | None = None,
    seed: int | None = None,
    metadata: dict[str, object] | None = None,
) -> MessageResponse:
    """Call the selected provider and return the structured response.

    ``provider`` overrides ``EVAL_PROVIDER``. The default uses Anthropic
    urllib; other values route through ``_providers``. Provider-controlled
    failure details and exception causes are not serialized.

    A non-default provider carries no Messages API stop metadata, so it
    returns termination ``"unknown"`` with an empty ``block_types`` and a
    ``None`` ``stop_reason`` (REQ-037 Data Model).
    """
    selected = provider if provider is not None else os.environ.get("EVAL_PROVIDER")
    alternate = _call_selected_provider(
        selected,
        messages,
        system,
        model,
        max_tokens,
        temperature,
        seed,
        metadata,
    )
    if alternate is not None:
        return MessageResponse(
            text=alternate,
            stop_reason=None,
            termination="unknown",
            block_types=(),
        )

    def _send(include_temperature: bool) -> object:
        request = _build_messages_request(
            api_key,
            messages,
            system,
            model,
            max_tokens,
            temperature if include_temperature else None,
        )
        return _read_messages_response(request, api_key)

    result = call_with_temperature_fallback(
        _send, lambda exc: isinstance(exc, TemperatureDeprecatedError)
    )
    if not isinstance(result, dict):
        raise RuntimeError(
            "Anthropic API returned an unexpected payload shape: "
            "error=invalid_response; provider response redacted"
        )
    return parse_message_response(result)


def call_api(
    api_key: str,
    messages: list[dict[str, str]],
    system: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
    temperature: float | None = 0.0,
    provider: str | None = None,
    seed: int | None = None,
    metadata: dict[str, object] | None = None,
) -> str:
    """Call the selected provider and return assistant text.

    Text view over `call_api_response` for the existing callers that read a
    string. When `metadata` is passed, this also writes `termination` and
    `stop_reason` into it, and `refusal_category` when the response is a
    refusal (REQ-037 AC-6). The returned text is unchanged from before
    REQ-037 for every response shape (REQ-037 AC-5).
    """
    response = call_api_response(
        api_key,
        messages,
        system,
        model,
        max_tokens,
        temperature,
        provider,
        seed,
        metadata,
    )
    if metadata is not None:
        metadata["termination"] = response.termination
        metadata["stop_reason"] = response.stop_reason
        if response.refusal_category is not None:
            metadata["refusal_category"] = response.refusal_category
    return response.text


def _parse_model_ids(result: object) -> list[str]:
    if not isinstance(result, dict):
        raise RuntimeError(
            "Anthropic models endpoint returned an unexpected payload shape: "
            "error=invalid_response; provider response redacted"
        )
    data = result.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError(
            "Anthropic models endpoint returned an unexpected 'data' shape: "
            "error=invalid_response; provider response redacted"
        )
    ids: list[str] = []
    for entry in data:
        model_id = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(model_id, str) or not model_id:
            raise RuntimeError(
                "Anthropic models endpoint returned a malformed model entry: "
                "error=invalid_response; provider response redacted"
            )
        ids.append(model_id)
    return ids


def list_available_models(api_key: str, *, timeout: int = 30) -> list[str]:
    """Return the model ids reachable with ``api_key`` via ``GET /v1/models``.

    Args:
        api_key: The Anthropic API key.
        timeout: Socket timeout in seconds.

    Returns:
        A list of model id strings (``data[].id``). May be empty if the
        account exposes no models.

    Raises:
        RuntimeError: On HTTP error, network failure, timeout, or invalid
            JSON. Provider-controlled details and exception causes are not
            serialized. Callers that want fail-open behavior on infrastructure
            errors should catch this.
    """
    req = urllib.request.Request(
        f"{_MODELS_ENDPOINT}?limit=1000",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode(errors="replace"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(safe_http_error_message("Anthropic models endpoint", e.code)) from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise RuntimeError(f"Anthropic models endpoint timed out after {timeout}s.") from None
        raise RuntimeError(
            "Anthropic models endpoint network error: error=network_failure; "
            "provider details redacted"
        ) from None
    except TimeoutError:
        raise RuntimeError(f"Anthropic models endpoint timed out after {timeout}s.") from None
    except json.JSONDecodeError:
        raise RuntimeError(
            "Anthropic models endpoint returned invalid JSON: "
            "error=invalid_json; provider response redacted"
        ) from None

    return _parse_model_ids(result)


def verify_model_available(
    api_key: str,
    model: str,
    *,
    provider: str | None = None,
    timeout: int = 30,
) -> None:
    """Fail fast before the first scored call if ``model`` is unreachable.

    Preflight for the eval harness (issue #2857). Semantics follow the repo
    fail-open/fail-closed doctrine:

    - **Protocol violation (fail-closed):** the key reaches ``/v1/models`` and
      ``model`` is not in the returned list -> raise ``RuntimeError`` without
      persisting provider-controlled model ids, so a live run never spends on
      a dead model id.
    - **Infrastructure error (fail-open):** the ``/v1/models`` lookup itself
      fails (network down, auth error, malformed body) -> print a warning to
      stderr and return, letting the run proceed and surface the real error
      (now 404-enriched) at first call rather than blocking on a flaky probe.

    No-ops when ``EVAL_SKIP_MODEL_PREFLIGHT`` is set (truthy) or when a
    non-default provider is selected (those adapters self-manage credentials
    and model routing).

    Args:
        api_key: The Anthropic API key. Ignored for non-anthropic providers.
        model: The model id the run intends to use.
        provider: Optional transport selector. ``None`` falls back to the
            ``EVAL_PROVIDER`` env var.
        timeout: Socket timeout in seconds for the probe.

    Raises:
        RuntimeError: If the model is provably unreachable (fail-closed).
    """
    if os.environ.get("EVAL_SKIP_MODEL_PREFLIGHT"):
        return

    selected = provider if provider is not None else os.environ.get("EVAL_PROVIDER")
    if selected:
        from _providers import is_default_anthropic

        if not is_default_anthropic(selected):
            return

    try:
        reachable = list_available_models(api_key, timeout=timeout)
    except RuntimeError as e:
        # Infrastructure error: fail open so a flaky probe cannot block a run.
        print(
            f"WARNING: model preflight skipped ({e}). "
            "Proceeding; a bad model id will surface at first API call.",
            file=sys.stderr,
        )
        return

    # A successful probe that does not list `model` means it is provably
    # unreachable with this key -> fail closed. An empty list is the same
    # signal (the probe worked and returned zero models), so it also fails
    # closed rather than silently proceeding to a guaranteed 404.
    if model not in reachable:
        raise RuntimeError(
            "Requested model is not reachable with this API key. "
            "Query the models endpoint and pass a reachable model ID."
        )


def load_custom_prompts(path: str) -> dict[str, list[dict[str, Any]]]:
    """Load prompts from a JSON file.

    The file may either contain a top-level mapping of ``{name: [prompts]}``
    or wrap it under a ``prompts`` key. Validates structural shape at the
    CLI boundary and raises ``RuntimeError`` with an actionable message on
    invalid input. Per-item content is trusted downstream.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("prompts"), dict):
        prompts = data["prompts"]
    else:
        prompts = data
    if not isinstance(prompts, dict):
        raise RuntimeError(
            f"Invalid prompts file {path}: expected top-level object mapping names to lists."
        )
    for name, items in prompts.items():
        if not isinstance(items, list):
            raise RuntimeError(
                f"Invalid prompts file {path}: entry '{name}' must map to a list of prompt objects."
            )
        for index, entry in enumerate(items):
            if not isinstance(entry, dict):
                raise RuntimeError(
                    f"Invalid prompts file {path}: entry '{name}' item {index} must be an object."
                )
    return prompts
