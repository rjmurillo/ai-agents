"""Multi-provider transport strategy for the eval harness.

DESIGN-004 §5.4 names a `Transport` seam: a callable that turns a
(prompt, model, system) triple into assistant text. `_anthropic_api.call_api`
is the original (urllib, Anthropic-only) transport. This module adds the
sibling providers so the same eval scripts can run against OpenAI and GitHub
Models when the `ANTHROPIC_API_KEY` budget is exhausted, selected by the
`EVAL_PROVIDER` environment variable or an explicit `--provider` flag.

Open/Closed: a new provider is a new class plus one row in `_REGISTRY`. No
edit to `call_api`, the retry/categorization adapter, or any eval script.

Error contract (load-bearing): every provider raises `RuntimeError` whose
message carries the same shapes `_anthropic_api.call_api` emits, so
`_eval_api_adapter._categorize_error` classifies them without change:
  - HTTP status:  "<Provider> API returned HTTP <code>: <short ascii excerpt>"
  - timeout:      "...timed out..."
  - other network: "<Provider> API network error: ..."

Cross-provider symmetry (ADR-058 "Experimental Design Symmetry"): a single
eval invocation runs the baseline and the variant through ONE provider. Scores
from different providers are not comparable; re-baseline per provider.

SDK dependency: OpenAI and GitHub Models use the `openai` package from the
`eval` optional extra (`pip install -e '.[eval]'`). The optional Anthropic-SDK
provider uses the repository's core `anthropic` dependency. The default
`anthropic` provider stays on the dependency-free urllib path in
`_anthropic_api`, so the default eval needs no SDK and existing baselines do not
move.

The `copilot-cli` provider needs no SDK and no API key at all: it shells out to
an authenticated GitHub Copilot CLI. That makes it the cheapest way to eval
against the exact models this repository's owner uses day to day, so prefer it
when the question is "does this change help the models we actually run."
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

# Sibling import; loaded under the same EVAL_DIR sys.path entry that the CLI
# uses. A package-qualified import would bind a second copy of the module
# when a caller has the repo root on sys.path, and a monkeypatch applied to
# one copy would not reach the other.
import _eval_api_adapter_constants as _constants
from _copilot_cli import _CopilotCLIProvider
from _eval_common import safe_http_error_message

# GitHub Models inference endpoint (OpenAI-compatible). Verified 2026-06:
# https://models.github.ai/inference with a GitHub PAT as the bearer token.
GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"

if TYPE_CHECKING:  # imported lazily at runtime; typed here for the client factory
    from anthropic.types import MessageParam
    from openai import OpenAI


class EvalProvider(Protocol):
    """Strategy interface. One method: text in, text out, normalized errors."""

    name: str
    system_fingerprint: str | None

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> str:
        """Return assistant text. Raise RuntimeError on any failure."""
        ...


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


def _normalize_and_raise(provider_label: str, exc: Exception) -> None:
    """Re-raise an SDK exception as a RuntimeError matching the message shapes
    `_eval_api_adapter._categorize_error` already understands."""
    name = type(exc).__name__.lower()
    if "timeout" in name:
        raise RuntimeError(
            f"{provider_label} API request timed out. The service may be slow or unreachable."
        ) from None
    code = _http_code_from_exc(exc)
    if code is not None:
        raise RuntimeError(safe_http_error_message(f"{provider_label} API", code)) from None
    raise RuntimeError(
        f"{provider_label} API network error: error=network_failure; provider details redacted"
    ) from None


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
    ) -> None:
        self.name = name
        self._provider_label = provider_label
        self._key_names = key_names
        self._base_url = base_url
        self.system_fingerprint: str | None = None

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
        client_factory = cast("Callable[..., OpenAI]", OpenAI)
        return client_factory(**kwargs)

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> str:
        client = self._client()
        self.system_fingerprint = None
        full_messages: list[dict[str, str]] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        # Reasoning models reject max_tokens + custom temperature; send
        # max_completion_tokens and omit temperature so o-series / gpt-5 work.
        create_kwargs: dict[str, object] = {"model": model, "messages": full_messages}
        if _is_reasoning_model(model):
            create_kwargs["max_completion_tokens"] = max_tokens
        else:
            create_kwargs["max_tokens"] = max_tokens
            create_kwargs["temperature"] = temperature
        if seed is not None:
            create_kwargs["seed"] = seed
        try:
            create_completion = cast("Callable[..., Any]", client.chat.completions.create)
            resp = create_completion(**create_kwargs)
        except Exception as exc:
            _normalize_and_raise(self._provider_label, exc)
            raise  # unreachable; _normalize_and_raise always raises
        choices = getattr(resp, "choices", None) or []
        if not choices:
            raise RuntimeError(
                f"{self._provider_label} API returned no choices; "
                "model identifier redacted"
            )
        content = choices[0].message.content
        if not isinstance(content, str):
            raise RuntimeError(
                f"{self._provider_label} API returned non-text content; "
                "model identifier redacted"
            )
        fingerprint = getattr(resp, "system_fingerprint", None)
        self.system_fingerprint = _constants.normalize_fingerprint(fingerprint)
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

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> str:
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
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system or "",
                messages=anthropic_messages,
                temperature=temperature,
            )
        except Exception as exc:
            _normalize_and_raise(self._provider_label, exc)
            raise  # unreachable
        parts = [
            block.text
            for block in getattr(resp, "content", [])
            if getattr(block, "type", None) == "text"
        ]
        return "".join(parts)


def _make_copilot_cli() -> EvalProvider:
    timeout = os.environ.get("COPILOT_CLI_TIMEOUT")
    kwargs: dict[str, object] = {}
    if timeout:
        try:
            parsed_timeout = float(timeout)
        except ValueError as exc:
            raise RuntimeError(
                f"COPILOT_CLI_TIMEOUT must be a number of seconds, got {timeout!r}."
            ) from exc
        if not math.isfinite(parsed_timeout) or parsed_timeout <= 0:
            raise RuntimeError(
                "COPILOT_CLI_TIMEOUT must be a finite positive number of seconds."
            )
        kwargs["timeout"] = parsed_timeout
    executable = os.environ.get("COPILOT_CLI_BIN")
    if executable:
        kwargs["executable"] = executable
    # The sibling import is a flat module rather than a package path, so mypy
    # resolves it to Any under `ignore_missing_imports`. Pin the contract at
    # this boundary instead of letting Any leak into the registry.
    provider: EvalProvider = _CopilotCLIProvider(**cast("dict[str, Any]", kwargs))
    return provider


def _make_openai() -> EvalProvider:
    return _OpenAICompatibleProvider(
        name="openai",
        provider_label="OpenAI",
        key_names=["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
    )


def _make_github() -> EvalProvider:
    return _OpenAICompatibleProvider(
        name="github",
        provider_label="GitHub Models",
        key_names=["GITHUB_MODELS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"],
        base_url=os.environ.get("GITHUB_MODELS_BASE_URL") or GITHUB_MODELS_BASE_URL,
    )


def _make_anthropic_sdk() -> EvalProvider:
    return _AnthropicSDKProvider()


# Open/Closed registry. New provider = new factory + one row here. Aliases let
# callers spell the same provider a few intuitive ways.
_REGISTRY: dict[str, Callable[[], EvalProvider]] = {
    "openai": _make_openai,
    "codex": _make_openai,
    "github": _make_github,
    "github-models": _make_github,
    "anthropic-sdk": _make_anthropic_sdk,
    "copilot": _make_copilot_cli,
    "copilot-cli": _make_copilot_cli,
}

# Provider names that mean "use the default urllib Anthropic path in
# `_anthropic_api.call_api`", i.e. NOT routed through this module.
DEFAULT_ANTHROPIC_NAMES = frozenset({"", "anthropic", "anthropic-http", "anthropic-urllib"})


def is_default_anthropic(name: str | None) -> bool:
    """True when `name` selects the built-in urllib Anthropic transport."""
    return (name or "").strip().lower() in DEFAULT_ANTHROPIC_NAMES


def known_provider_names() -> list[str]:
    """Sorted list of every selectable provider name (for --help / errors)."""
    return sorted((DEFAULT_ANTHROPIC_NAMES - {""}) | set(_REGISTRY))


def resolve_provider(name: str | None = None) -> EvalProvider:
    """Return the provider for `name` (or `EVAL_PROVIDER`, default anthropic).

    Raises RuntimeError naming the valid choices when `name` is unknown. The
    default-anthropic names are rejected here because they are handled by
    `_anthropic_api.call_api` directly, not through a provider object.
    """
    selected = (name or os.environ.get("EVAL_PROVIDER") or "anthropic").strip().lower()
    if is_default_anthropic(selected):
        raise RuntimeError(
            f"Provider '{selected}' is the built-in urllib Anthropic transport; "
            "call `_anthropic_api.call_api` directly instead of resolve_provider()."
        )
    factory = _REGISTRY.get(selected)
    if factory is None:
        raise RuntimeError(
            f"Unknown EVAL_PROVIDER '{selected}'. Valid: " + ", ".join(known_provider_names())
        )
    return factory()
