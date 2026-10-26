"""HTTP transports for the eval harness: Anthropic and OpenAI-compatible.

Split out of `_providers` when the billing matrix landed and that module
crossed the 500-line taste ceiling. The seam is what changes together: an
HTTP status code, an SDK keyword argument, or a reasoning-model quirk changes
things here and nothing in the registry; a new matrix cell changes the
registry and nothing here.

Nothing in this module imports `_providers`, so the dependency runs one way
and an import cycle is ruled out. `_providers.resolve_provider` remains the
only supported entry point for callers; import these classes directly only
from tests.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

# Sibling import; loaded under the same EVAL_DIR sys.path entry that the CLI
# uses. A package-qualified import would bind a second copy of the module
# when a caller has the repo root on sys.path, and a monkeypatch applied to
# one copy would not reach the other.
import _eval_api_adapter_constants as _constants
from _eval_common import (
    call_with_temperature_fallback,
    is_temperature_deprecated_message,
    safe_http_error_message,
)

if TYPE_CHECKING:  # imported lazily at runtime; typed here for the client factory
    from anthropic.types import MessageParam
    from openai import OpenAI

# GitHub Models inference endpoint (OpenAI-compatible). Verified 2026-06:
# https://models.github.ai/inference with a GitHub PAT as the bearer token.
# Retired 2026-07-30; the endpoint answered HTTP 410 when re-probed
# 2026-09-16. Kept so an archived run's provider string still resolves.
GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"
# The openai SDK's own default endpoint, named so an empty OPENAI_BASE_URL can
# be replaced with it: the SDK would otherwise read the empty string itself.
OPENAI_API_BASE_URL = "https://api.openai.com/v1"

__all__ = [
    "GITHUB_MODELS_BASE_URL",
    "OPENAI_API_BASE_URL",
    "OpenAIUsage",
    "_AnthropicSDKProvider",
    "_OpenAICompatibleProvider",
    "_http_code_from_exc",
    "_is_reasoning_model",
    "_is_temperature_deprecated_sdk_error",
    "_normalize_and_raise",
    "_read_env_key",
    "weighted_input_cost_units",
]


def _read_env_key(names: list[str]) -> str:
    """Resolve the first present key among `names` from the environment, then
    the repo-root `.env`. Mirrors `_anthropic_api.load_api_key` for arbitrary
    key names. Raises RuntimeError naming every candidate when none is found.
    """
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    # Repo-root .env fallback. Mirror _anthropic_api.load_api_key's symlink
    # defense so an attacker-controlled module path cannot redirect credential
    # lookup outside the repository.
    raw = Path(__file__)
    if raw.is_symlink():
        raise RuntimeError(
            "API key load aborted: refusing to resolve symlinked module path (CWE-22 defense)."
        )
    env_path = raw.resolve(strict=True).parents[2] / ".env"
    if env_path.is_file() and not env_path.is_symlink():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, val = stripped.partition("=")
            if key.strip() in names:
                resolved = val.strip()
                if (
                    len(resolved) >= 2
                    and resolved[0] == resolved[-1]
                    and resolved[0]
                    in (
                        '"',
                        "'",
                    )
                ):
                    resolved = resolved[1:-1]
                if resolved:
                    return resolved
    raise RuntimeError(
        "No API key found for provider. Looked for "
        + ", ".join(names)
        + " in the environment and the repo-root .env file."
    )


def _http_code_from_exc(exc: Exception) -> int | None:
    """Best-effort HTTP status extraction from an SDK exception.

    The OpenAI and Anthropic SDKs both expose `.status_code` on their
    `APIStatusError` family. Fall back to None for connection/timeout errors
    that carry no status.
    """
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    return code if isinstance(code, int) else None


def _body_from_exc(exc: Exception) -> object:
    """Return the SDK exception's parsed body, falling back to its message text.

    The result feeds `safe_http_error_message`, which reads only `error.type`
    and the billing verdict from it; nothing here is returned to a caller.
    """
    body = getattr(exc, "body", None)
    if body is not None:
        return body
    message = getattr(exc, "message", None)
    return message if isinstance(message, str) else None


def _normalize_and_raise(provider_label: str, exc: Exception) -> None:
    """Re-raise an SDK exception as a RuntimeError matching the message shapes
    `_eval_api_adapter._categorize_error` already understands.

    Order matters: a `TypeError` (the SDK's own call rejected an argument
    this provider sent, e.g. a keyword an installed SDK version removed) is
    not a network condition and must not fall through to the
    `network_failure` label below, which used to hide exactly that failure
    behind a misleading message.
    """
    name = type(exc).__name__.lower()
    if "timeout" in name:
        raise RuntimeError(
            f"{provider_label} API request timed out. The service may be slow or unreachable."
        ) from None
    if isinstance(exc, TypeError):
        raise RuntimeError(
            f"{provider_label} SDK call raised TypeError: error=sdk_argument_mismatch; "
            "the installed SDK version does not accept an argument this provider sends"
        ) from None
    code = _http_code_from_exc(exc)
    if code is not None:
        raise RuntimeError(
            safe_http_error_message(f"{provider_label} API", code, _body_from_exc(exc))
        ) from None
    raise RuntimeError(
        f"{provider_label} API network error: error=network_failure; provider details redacted"
    ) from None


def _is_temperature_deprecated_sdk_error(exc: Exception) -> bool:
    """True for the SDK's `BadRequestError` shape of a deprecated-temperature
    400. Gated on status code 400 first so an unrelated message never
    triggers the fallback retry by accident."""
    if _http_code_from_exc(exc) != 400:
        return False
    message = getattr(exc, "message", None)
    if not isinstance(message, str):
        message = str(exc)
    # bool(...): `_eval_common` is a sibling module reached through the same
    # bare sys.path import every function in this file already uses, which
    # mypy cannot resolve without a package `__init__.py` and reads as `Any`
    # under `ignore_missing_imports`. The function itself is typed `-> bool`;
    # this only satisfies `no-any-return` at the call site.
    return bool(is_temperature_deprecated_message(message))


# OpenAI reasoning models (o1/o3/o4 series, gpt-5 and gpt-6 families) reject
# `max_tokens` and a non-default `temperature` with HTTP 400; they require
# `max_completion_tokens` and the provider's default temperature. Match by id,
# tolerating a vendor prefix like "openai/". A new reasoning family is one more
# alternative in this pattern, no other change.
# gpt-6 covers `gpt-6-astra`, whose migration guide drops `temperature`,
# `top_p`, and `top_logprobs`.
_REASONING_MODEL_RE = re.compile(r"^(?:[a-z0-9-]+/)?(?:o\d|gpt-[56])", re.IGNORECASE)


def _is_reasoning_model(model: str) -> bool:
    """True for OpenAI reasoning models that need max_completion_tokens."""
    return bool(_REASONING_MODEL_RE.match(model or ""))


# `prompt_cache_options` and `prompt_cache_breakpoint` exist for GPT-5.6 and
# later. Version is major or major.minor followed by end, `-`, or `.`, so
# `gpt-5.6-mini`, `gpt-5.10`, `gpt-6-luna`, and `openai/gpt-7` match while
# `gpt-5.5`, `gpt-5.60x`, `gpt-5`, and `gpt-4o` do not.
_PROMPT_CACHE_MODEL_RE = re.compile(
    r"^(?:[a-z0-9-]+/)?gpt-(\d+)(?:\.(\d+))?(?=$|[-.])", re.IGNORECASE
)
_PROMPT_CACHE_MIN_MAJOR = 6
_PROMPT_CACHE_MIN_MINOR_AT_FIVE = 6
_EXPLICIT_CACHE_MODE: dict[str, str] = {"mode": "explicit"}


def _supports_prompt_cache_options(model: str) -> bool:
    """True for GPT-5.6 and later, which accept explicit prompt caching."""
    match = _PROMPT_CACHE_MODEL_RE.match(model or "")
    if match is None:
        return False
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if major >= _PROMPT_CACHE_MIN_MAJOR:
        return True
    return major == 5 and minor >= _PROMPT_CACHE_MIN_MINOR_AT_FIVE


@dataclass(frozen=True, slots=True)
class OpenAIUsage:
    """Token counts from one Chat Completions response (`resp.usage`).

    Every field is `None` when the response did not report it. `None` means
    "not reported" and must never be read as zero: a provider that omits
    `prompt_tokens_details` has not said that nothing was cached.
    """

    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None
    cache_write_tokens: int | None


def _count_or_none(value: object) -> int | None:
    """A real non-negative int, else None. `bool` is an int subclass, so refuse it."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _parse_usage(usage: object) -> OpenAIUsage | None:
    """Read `usage` off an SDK response without trusting its shape."""
    if usage is None:
        return None
    details = getattr(usage, "prompt_tokens_details", None)
    return OpenAIUsage(
        prompt_tokens=_count_or_none(getattr(usage, "prompt_tokens", None)),
        completion_tokens=_count_or_none(getattr(usage, "completion_tokens", None)),
        cached_tokens=_count_or_none(getattr(details, "cached_tokens", None)),
        cache_write_tokens=_count_or_none(getattr(details, "cache_write_tokens", None)),
    )


def weighted_input_cost_units(
    usage: OpenAIUsage,
    *,
    read_multiplier: float = 0.1,
    write_multiplier: float = 1.25,
) -> float | None:
    """Input cost in uncached-token units, per the OpenAI prompt caching guide.

    ordinary = prompt - cached - write; weighted = ordinary +
    cached * read_multiplier + write * write_multiplier. Defaults are the
    30-minute rates for most GPT-5.6+ models (pass read_multiplier=0.05 for
    GPT-6.1 Sol), from
    https://developers.openai.com/api/docs/guides/prompt-caching. Returns None
    when any needed count is unreported, because a guessed zero would price a
    cache hit or write as free. Carries no price table: multiply by the model's
    uncached input price outside.
    """
    prompt = usage.prompt_tokens
    cached = usage.cached_tokens
    written = usage.cache_write_tokens
    if prompt is None or cached is None or written is None:
        return None
    ordinary = prompt - cached - written
    if ordinary < 0:
        # Cached plus written cannot exceed the prompt; a response that says
        # so is malformed, and pricing it would report a negative cost.
        return None
    return ordinary + cached * read_multiplier + written * write_multiplier


class _OpenAICompatibleProvider:
    """OpenAI Chat Completions transport. Backs both the OpenAI provider and
    the GitHub Models provider (GitHub Models mirrors the OpenAI API, differing
    only in base URL and credential). The Anthropic-style separate `system`
    argument is folded into a leading system-role message.
    """

    def __init__(
        self,
        *,
        name: str,
        provider_label: str,
        key_names: list[str],
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
        explicit_prompt_cache: bool = False,
    ) -> None:
        self.name = name
        self._explicit_prompt_cache = explicit_prompt_cache
        self._provider_label = provider_label
        self._key_names = key_names
        self._base_url = base_url
        self._default_headers = default_headers
        self.system_fingerprint: str | None = None
        self.usage: OpenAIUsage | None = None
        # The request carries `max_tokens`, so a long answer can be cut (#5405).
        self.applies_max_tokens = True
        self.finish_reason: str | None = None

    def _client(self) -> OpenAI:
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover - env-dependent
            raise RuntimeError(
                f"The 'openai' package is required for the {self.name} provider. "
                "Install the eval extra: pip install -e '.[eval]'."
            ) from exc
        api_key = _read_env_key(self._key_names)
        kwargs: dict[str, object] = {"api_key": api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        # release-it: explicit timeout on every outbound call. max_retries=0
        # because the adapter owns the retry policy; an SDK retry layer here
        # would be nested retries. 120s matches the urllib path.
        kwargs["timeout"] = 120.0
        kwargs["max_retries"] = 0
        if self._default_headers:
            kwargs["default_headers"] = dict(self._default_headers)
        client_factory = cast("Callable[..., OpenAI]", OpenAI)
        return client_factory(**kwargs)

    @staticmethod
    def _cached_system_message(system: str) -> dict[str, Any]:
        # Guide: https://developers.openai.com/api/docs/guides/prompt-caching
        # GPT-5.6+ defaults to implicit mode: the breakpoint sits at the end of
        # the latest user message and the write costs 1.25x input. With a fixed
        # system prompt and a changing user message, that pays the write on
        # every call and the next request never reuses the system prefix
        # (guide "Gotchas"). Explicit mode with a breakpoint after the system
        # prompt caches only the stable prefix; the user message bills at the
        # uncached rate with no write charge. Explicit mode with no breakpoint
        # (empty system) makes no cache writes at all. A prefix under 1,024
        # tokens is never cached, so a short system prompt costs nothing extra.
        part = {
            "type": "text",
            "text": system,
            "prompt_cache_breakpoint": dict(_EXPLICIT_CACHE_MODE),
        }
        return {"role": "system", "content": [part]}

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float | None = 0.0,
        seed: int | None = None,
    ) -> str:
        # Reset before building the client so a credential or import failure
        # cannot leave the previous call's metadata in place.
        self.system_fingerprint = None
        self.finish_reason = None
        self.usage = None
        client = self._client()
        full_messages: list[dict[str, Any]] = []
        use_explicit_cache = self._explicit_prompt_cache and _supports_prompt_cache_options(model)
        if system and use_explicit_cache:
            full_messages.append(self._cached_system_message(system))
        elif system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        # Reasoning models reject max_tokens + custom temperature; send
        # max_completion_tokens and omit temperature so o-series / gpt-5 work.
        create_kwargs: dict[str, object] = {"model": model, "messages": full_messages}
        if _is_reasoning_model(model):
            create_kwargs["max_completion_tokens"] = max_tokens
        else:
            create_kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                create_kwargs["temperature"] = temperature
        if seed is not None:
            create_kwargs["seed"] = seed
        if use_explicit_cache:
            create_kwargs["prompt_cache_options"] = dict(_EXPLICIT_CACHE_MODE)
        try:
            create_completion = cast("Callable[..., Any]", client.chat.completions.create)
            resp = create_completion(**create_kwargs)
        except Exception as exc:
            _normalize_and_raise(self._provider_label, exc)
            raise  # unreachable; _normalize_and_raise always raises
        choices = getattr(resp, "choices", None) or []
        if not choices:
            raise RuntimeError(
                f"{self._provider_label} API returned no choices; model identifier redacted"
            )
        content = choices[0].message.content
        if not isinstance(content, str):
            raise RuntimeError(
                f"{self._provider_label} API returned non-text content; model identifier redacted"
            )
        fingerprint = getattr(resp, "system_fingerprint", None)
        self.system_fingerprint = _constants.normalize_fingerprint(fingerprint)
        finish_reason = getattr(choices[0], "finish_reason", None)
        self.finish_reason = finish_reason if isinstance(finish_reason, str) else None
        self.usage = _parse_usage(getattr(resp, "usage", None))
        return content


class _AnthropicSDKProvider:
    """Anthropic Messages transport via the official `anthropic` SDK.

    Optional alternative to the default urllib path in `_anthropic_api`. Select
    with EVAL_PROVIDER=anthropic-sdk. The default `anthropic` provider stays on
    urllib so the zero-dependency baseline is preserved.
    """

    name = "anthropic-sdk"
    _provider_label = "Anthropic"
    system_fingerprint: str | None = None
    # The request carries `max_tokens`, so a long answer can be cut (#5405).
    applies_max_tokens = True
    finish_reason: str | None = None

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float | None = 0.0,
        seed: int | None = None,
    ) -> str:
        self.finish_reason = None
        try:
            from anthropic import Anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "The 'anthropic' package is required for the anthropic-sdk "
                "provider. Install the project dependencies from pyproject.toml."
            ) from exc
        api_key = _read_env_key(["ANTHROPIC_API_KEY"])
        client = Anthropic(api_key=api_key, timeout=120.0, max_retries=0)
        anthropic_messages = cast("Iterable[MessageParam]", messages)
        # `temperature` is not a typed parameter of `messages.create` in SDK
        # >=1.x (anthropic 1.6.0 dropped it from every overload; Anthropic is
        # deprecating the field per model). Passing it as a direct keyword
        # raises TypeError regardless of model. `extra_body` merges it into
        # the raw JSON request body instead, bypassing the typed schema, so
        # models that still accept the field (see the comment above
        # `_eval_common._TEMPERATURE_DEPRECATED_RE` for the current split)
        # keep getting it. A `None` temperature is omitted entirely.
        create_message = cast("Callable[..., Any]", client.messages.create)

        def _send(include_temperature: bool) -> object:
            kwargs: dict[str, object] = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system or "",
                "messages": anthropic_messages,
            }
            if include_temperature and temperature is not None:
                kwargs["extra_body"] = {"temperature": temperature}
            return create_message(**kwargs)

        try:
            resp = call_with_temperature_fallback(_send, _is_temperature_deprecated_sdk_error)
        except Exception as exc:
            _normalize_and_raise(self._provider_label, exc)
            raise  # unreachable
        parts = [
            block.text
            for block in getattr(resp, "content", [])
            if getattr(block, "type", None) == "text"
        ]
        stop_reason = getattr(resp, "stop_reason", None)
        self.finish_reason = stop_reason if isinstance(stop_reason, str) else None
        return "".join(parts)
