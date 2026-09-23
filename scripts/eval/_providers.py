"""Multi-provider transport strategy for the eval harness.

DESIGN-004 §5.4 names a `Transport` seam: a callable that turns a
(prompt, model, system) triple into assistant text. `_anthropic_api.call_api`
is the original (urllib, Anthropic-only) transport. This module holds the
sibling providers, selected by the `EVAL_PROVIDER` environment variable or an
explicit `--provider` flag.

`_billing_matrix` is what those names mean. Every selectable row here belongs
to one (harness, billing) cell of that table, and `registry_classification_gaps`
exists so a row added without a cell is caught by a test rather than inheriting
a billing model by silence. Read the table first; this module is how its cells
are dispatched.

Open/Closed: a new provider is a new class, one row in `_REGISTRY`, and one
cell in the matrix. No edit to `call_api`, the retry/categorization adapter, or
any eval script.

Error contract (load-bearing): every provider raises `RuntimeError` whose
message carries the same shapes `_anthropic_api.call_api` emits, so
`_eval_api_adapter._categorize_error` classifies them without change:
  - HTTP status:  "<Provider> API returned HTTP <code>: <short ascii excerpt>"
  - timeout:      "...timed out..."
  - other network: "<Provider> API network error: ..."

Cross-provider symmetry (ADR-058 "Experimental Design Symmetry"): a single
eval invocation runs the baseline and the variant through ONE provider. Scores
from different providers are not comparable; re-baseline per provider.

SDK dependency: the OpenAI-compatible providers use the `openai` package from
the `eval` optional extra (`pip install -e '.[eval]'`). The optional
Anthropic-SDK provider uses the repository's core `anthropic` dependency. The
default `anthropic` provider stays on the dependency-free urllib path in
`_anthropic_api`, so the default eval needs no SDK and existing baselines do
not move.

The three subscription providers (`claude-cli`, `codex-cli`, `copilot-cli`)
need no SDK and no API key: they shell out to a CLI the operator is already
signed in to, and each one strips the metered credentials from the child so
the run cannot quietly fall back onto a billed account. That makes them the
cheapest way to eval against the exact models this repository's owner uses day
to day, so prefer them when the question is "does this change help the models
we actually run." Their transports live in `_claude_cli`, `_codex_cli`, and
`_copilot_cli`; this module only builds them.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from typing import Any, Protocol, cast

# Sibling import; loaded under the same EVAL_DIR sys.path entry that the CLI
# uses. A package-qualified import would bind a second copy of the module
# when a caller has the repo root on sys.path, and a monkeypatch applied to
# one copy would not reach the other.
from _billing_matrix import cell_for_provider
from _claude_cli import _ClaudeCLIProvider
from _codex_cli import _CodexCLIProvider
from _copilot_cli import _CopilotCLIProvider

# Re-exported rather than re-implemented. Callers and tests reach the HTTP
# transports through this module because `resolve_provider` lives here; the
# implementations moved to keep this file under the file-size ceiling.
from _http_providers import (
    GITHUB_MODELS_BASE_URL,
    _AnthropicSDKProvider,
    _http_code_from_exc,
    _is_reasoning_model,
    _normalize_and_raise,
    _OpenAICompatibleProvider,
    _read_env_key,
)

# The re-exports above are part of this module's surface, not leftovers, so
# they are named here: a lint pass that prunes unused imports would otherwise
# break every caller that reaches an HTTP transport through `_providers`.
__all__ = [
    "COPILOT_API_BASE_URL_ENV",
    "COPILOT_API_HEADERS_ENV",
    "DEFAULT_ANTHROPIC_NAMES",
    "GITHUB_MODELS_BASE_URL",
    "UNCLASSIFIED_LEGACY_PROVIDERS",
    "EvalProvider",
    "_AnthropicSDKProvider",
    "_ClaudeCLIProvider",
    "_CodexCLIProvider",
    "_CopilotCLIProvider",
    "_OpenAICompatibleProvider",
    "_http_code_from_exc",
    "_is_reasoning_model",
    "_normalize_and_raise",
    "_read_env_key",
    "is_default_anthropic",
    "known_provider_names",
    "registry_classification_gaps",
    "resolve_provider",
]


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
        temperature: float | None = 0.0,
        seed: int | None = None,
    ) -> str:
        """Return assistant text. Raise RuntimeError on any failure."""
        ...


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
    # Same Any boundary the Copilot factory pins: `_http_providers` is a flat
    # sibling module, so its classes resolve to Any. Bind the contract here.
    provider: EvalProvider = _OpenAICompatibleProvider(
        name="openai",
        provider_label="OpenAI",
        key_names=["OPENAI_API_KEY"],
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
    )
    return provider


def _make_github() -> EvalProvider:
    provider: EvalProvider = _OpenAICompatibleProvider(
        name="github",
        provider_label="GitHub Models",
        key_names=["GITHUB_MODELS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"],
        base_url=os.environ.get("GITHUB_MODELS_BASE_URL") or GITHUB_MODELS_BASE_URL,
    )
    return provider


def _make_anthropic_sdk() -> EvalProvider:
    provider: EvalProvider = _AnthropicSDKProvider()
    return provider


#: The copilot/api cell names no endpoint by default, on purpose. GitHub
#: Models used to fill it and was retired on 2026-07-30; probed 2026-08-02 it
#: returns HTTP 410. No other GitHub-billed, OpenAI-compatible endpoint is
#: documented in a primary source this repository has read, so a baked-in
#: default would be a guess wearing a constant's clothes. The operator supplies
#: the base URL they are entitled to use, and an unset variable refuses the run
#: with the reason rather than silently calling api.openai.com on an
#: OPENAI_API_KEY, which would put an OpenAI-billed run in a Copilot cell.
COPILOT_API_BASE_URL_ENV = "COPILOT_API_BASE_URL"
COPILOT_API_HEADERS_ENV = "COPILOT_API_HEADERS"


def _make_copilot_api() -> EvalProvider:
    base_url = (os.environ.get(COPILOT_API_BASE_URL_ENV) or "").strip()
    if not base_url:
        raise RuntimeError(
            "The copilot-api provider has no default endpoint. GitHub Models, "
            "the endpoint that used to serve this cell, was retired on "
            "2026-07-30 and returns HTTP 410, and this repository has verified "
            "no replacement from a primary source. Set "
            f"{COPILOT_API_BASE_URL_ENV} to the OpenAI-compatible base URL your "
            "account is entitled to use, or select copilot-cli for the "
            "subscription cell."
        )
    provider: EvalProvider = _OpenAICompatibleProvider(
        name="copilot-api",
        provider_label="Copilot API",
        key_names=["COPILOT_API_KEY", "GITHUB_COPILOT_TOKEN"],
        base_url=base_url,
        default_headers=_copilot_api_headers(),
    )
    return provider


def _copilot_api_headers() -> dict[str, str] | None:
    """Return operator-supplied request headers for the copilot/api cell.

    Community projects that reach `api.githubcopilot.com` send headers such as
    `Copilot-Integration-Id` and `Editor-Version`. No GitHub documentation
    commits to those names, so hard-coding them would put a reverse-engineered
    contract in a constant where the next reader would mistake it for a
    verified one. The operator supplies whatever their gateway requires, as a
    JSON object, and an unparseable value fails the run instead of being
    dropped.
    """
    raw = (os.environ.get(COPILOT_API_HEADERS_ENV) or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{COPILOT_API_HEADERS_ENV} must be a JSON object mapping header "
            "names to string values."
        ) from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in parsed.items()
    ):
        raise RuntimeError(
            f"{COPILOT_API_HEADERS_ENV} must be a JSON object mapping header "
            "names to string values."
        )
    return parsed


def _cli_kwargs(timeout_env: str, bin_env: str) -> dict[str, object]:
    """Read the shared executable and timeout overrides for a CLI transport."""
    kwargs: dict[str, object] = {}
    timeout = os.environ.get(timeout_env)
    if timeout:
        try:
            parsed_timeout = float(timeout)
        except ValueError as exc:
            raise RuntimeError(
                f"{timeout_env} must be a number of seconds, got {timeout!r}."
            ) from exc
        if not math.isfinite(parsed_timeout) or parsed_timeout <= 0:
            raise RuntimeError(
                f"{timeout_env} must be a finite positive number of seconds."
            )
        kwargs["timeout"] = parsed_timeout
    executable = os.environ.get(bin_env)
    if executable:
        kwargs["executable"] = executable
    return kwargs


def _make_claude_cli() -> EvalProvider:
    kwargs = _cli_kwargs("CLAUDE_CLI_TIMEOUT", "CLAUDE_CLI_BIN")
    provider: EvalProvider = _ClaudeCLIProvider(**cast("dict[str, Any]", kwargs))
    return provider


def _make_codex_cli() -> EvalProvider:
    kwargs = _cli_kwargs("CODEX_CLI_TIMEOUT", "CODEX_CLI_BIN")
    provider: EvalProvider = _CodexCLIProvider(**cast("dict[str, Any]", kwargs))
    return provider


# Open/Closed registry. New provider = new factory + one row here. Aliases let
# callers spell the same provider a few intuitive ways.
_REGISTRY: dict[str, Callable[[], EvalProvider]] = {
    # claude / api is absent on purpose: it is the built-in urllib transport
    # in `_anthropic_api`, reached through DEFAULT_ANTHROPIC_NAMES below, so
    # no baseline measured on it moves. `anthropic-sdk` is the same cell
    # through the official SDK.
    "anthropic-sdk": _make_anthropic_sdk,
    # claude / subscription
    "claude-cli": _make_claude_cli,
    "claude-code": _make_claude_cli,
    "claude-subscription": _make_claude_cli,
    # codex / api
    "openai": _make_openai,
    "codex": _make_openai,
    "codex-api": _make_openai,
    # codex / subscription
    "codex-cli": _make_codex_cli,
    "codex-subscription": _make_codex_cli,
    # copilot / api
    "copilot-api": _make_copilot_api,
    # copilot / subscription
    "copilot": _make_copilot_cli,
    "copilot-cli": _make_copilot_cli,
    "copilot-subscription": _make_copilot_cli,
    # Retired. GitHub Models returns HTTP 410 since 2026-07-30. The rows stay
    # so an archived run's provider string still resolves to the transport it
    # was recorded on; do not select them.
    "github": _make_github,
    "github-models": _make_github,
}

# Provider names that mean "use the default urllib Anthropic path in
# `_anthropic_api.call_api`", i.e. NOT routed through this module.
DEFAULT_ANTHROPIC_NAMES = frozenset(
    {"", "anthropic", "anthropic-http", "anthropic-urllib", "claude-api"}
)


#: Registry rows that predate the billing matrix and are deliberately outside
#: it. The matrix lists cells an operator should select; GitHub Models has
#: returned HTTP 410 since its 2026-07-30 retirement, re-confirmed 2026-09-16,
#: so it is reachable history rather than a choice.
UNCLASSIFIED_LEGACY_PROVIDERS = frozenset({"github", "github-models"})


def registry_classification_gaps() -> frozenset[str]:
    """Return registry names that no billing-matrix cell claims.

    An unclassified transport gets its biller decided by the `cost_basis`
    default, which answers "usd" for anything it does not recognize. That
    default is right for an unknown name and wrong for a name this tool can
    dispatch to: omitting `copilot-cli` from the quota set is what once made a
    subscription CLI quote a Claude Sonnet token rate. Returning the gaps
    rather than raising at import keeps the check in a test, where a failure
    names the missing row instead of breaking every import of this module.
    """
    selectable = set(_REGISTRY) | (DEFAULT_ANTHROPIC_NAMES - {""})
    return frozenset(
        name
        for name in selectable - UNCLASSIFIED_LEGACY_PROVIDERS
        if cell_for_provider(name) is None
    )


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
