"""Shared Anthropic API utilities for evaluation scripts.

This module provides common functions for loading API keys, calling the
Anthropic Messages API, and loading custom prompt JSON files. Used by
eval-agents.py and eval-knowledge-integration.py.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

# Sibling import; loaded under the same EVAL_DIR sys.path entry every caller
# of this module already uses to reach it by bare name.
from _eval_common import require_str_or_none

# Single source of truth for the default eval model. Every eval script imports
# this instead of hard-coding an id, so a model bump is a one-line change here
# (issue #2858). The previous default `claude-sonnet-4-20250514` is a dead id
# that returns HTTP 404 against a current key; `claude-sonnet-4-6` is reachable
# and priced in `_eval_common.py`.
DEFAULT_MODEL = "claude-sonnet-4-6"

_MODELS_ENDPOINT = "https://api.anthropic.com/v1/models"


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


def call_api(
    api_key: str,
    messages: list[dict[str, str]],
    system: str = "",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    provider: str | None = None,
    seed: int | None = None,
    metadata: dict[str, object] | None = None,
) -> str:
    """Call the Anthropic Messages API.

    Args:
        api_key: The Anthropic API key.
        messages: List of message dicts with 'role' and 'content' keys.
        system: Optional system prompt.
        model: Model identifier to use.
        max_tokens: Maximum tokens in the response.
        temperature: Sampling temperature to send to the provider.
        provider: Optional transport selector. None falls back to the
            EVAL_PROVIDER env var. The default (None / "anthropic") uses this
            urllib path unchanged; any other value routes through
            `_providers.resolve_provider` (openai, github, anthropic-sdk).
            `api_key` is ignored for non-Anthropic providers.
        seed: Optional seed forwarded to OpenAI-compatible providers. None
            omits the argument.
        metadata: Optional output mapping for provider response metadata such
            as OpenAI-compatible `system_fingerprint`.

    Returns:
        The assistant's text response.

    Raises:
        RuntimeError: If the API returns an HTTP error, network failure,
            timeout, or invalid JSON response. Original exception is chained
            via __cause__.
    """
    selected = provider if provider is not None else os.environ.get("EVAL_PROVIDER")
    if selected is not None:
        from _providers import is_default_anthropic, resolve_provider

        if not is_default_anthropic(selected):
            selected_provider = resolve_provider(selected)
            kwargs: dict[str, object] = {
                "messages": messages,
                "system": system,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
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
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        # Determinism: the eval pipeline depends on temperature=0 so the
        # spike output-shape contract (verdict-vocabulary suffix) is
        # reproducible across reruns. Callers MAY override but MUST
        # justify in a comment if they do.
        "temperature": temperature,
    }
    if system:
        body["system"] = system

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode(errors="replace"))
    except urllib.error.HTTPError as e:
        # CWE-200 mitigation: the response body may contain echoed
        # request fragments, prompt content, or other sensitive data.
        # Surface the HTTP status and a short, ASCII-only excerpt so
        # adapter logs cannot leak prompts. The adapter only forwards
        # `error_category` to its structured log, but `_categorize_error`
        # also matches the `"HTTP <code>"` substring of this message,
        # which we preserve verbatim.
        try:
            raw_body = e.read().decode(errors="replace")
        except Exception:  # noqa: BLE001 - body read is best-effort only
            raw_body = ""
        sanitized = "".join(ch for ch in raw_body if 32 <= ord(ch) < 127)[:200]
        message = f"Anthropic API returned HTTP {e.code}: {sanitized}"
        if e.code == 404:
            # Bind the name here regardless of whether the provider fast-path
            # above ran (that import is guarded by `selected is not None`).
            # Keeps static analysis clean and the reference unambiguous.
            from _providers import is_default_anthropic

            if provider is None or is_default_anthropic(selected or ""):
                # A 404 on the messages endpoint almost always means the model id
                # is unknown to this key (issue #2857). Turn the bare 404 into an
                # actionable message that lists the ids the key can actually reach.
                # Best-effort only: never let the enrichment lookup raise.
                try:
                    reachable = list_available_models(api_key)
                    if reachable:
                        message += (
                            f". Model '{model}' may be unavailable; reachable ids: "
                            f"{', '.join(sorted(reachable))}"
                        )
                except Exception as enrich_err:  # noqa: BLE001 - enrichment is best-effort
                    print(
                        f"warning: reachable-model lookup failed: {enrich_err}",
                        file=sys.stderr,
                    )
        raise RuntimeError(message) from e
    except urllib.error.URLError as e:
        # urllib often wraps socket.timeout in URLError.reason; classify it
        # as a timeout so the error message is actionable.
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise RuntimeError(
                "Anthropic API request timed out after 120s. "
                "The service may be slow or unreachable."
            ) from e
        raise RuntimeError(
            f"Anthropic API network error: {e.reason}. "
            "Check connectivity and DNS resolution."
        ) from e
    except TimeoutError as e:
        raise RuntimeError(
            "Anthropic API request timed out after 120s. "
            "The service may be slow or unreachable."
        ) from e
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Anthropic API returned invalid JSON: {e.msg} at position {e.pos}. "
            "Response may be truncated or malformed."
        ) from e

    text_parts = [
        block["text"] for block in result.get("content", [])
        if block.get("type") == "text"
    ]
    return "\n".join(text_parts)


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
            JSON. Original exception chained via ``__cause__``. Callers that
            want fail-open behavior on infrastructure errors should catch this.
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
        try:
            raw_body = e.read().decode(errors="replace")
        except Exception:  # noqa: BLE001 - body read is best-effort only
            raw_body = ""
        sanitized = "".join(ch for ch in raw_body if 32 <= ord(ch) < 127)[:200]
        raise RuntimeError(
            f"Anthropic models endpoint returned HTTP {e.code}: {sanitized}"
        ) from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            raise RuntimeError(
                f"Anthropic models endpoint timed out after {timeout}s."
            ) from e
        raise RuntimeError(
            f"Anthropic models endpoint network error: {e.reason}."
        ) from e
    except TimeoutError as e:
        raise RuntimeError(
            f"Anthropic models endpoint timed out after {timeout}s."
        ) from e
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Anthropic models endpoint returned invalid JSON: {e.msg}."
        ) from e

    # A 200 with valid JSON can still be the wrong shape (a bare list, a
    # string, or a non-list `data`). Treat any shape violation as an
    # infrastructure error (RuntimeError) so callers fail open rather than
    # crashing on an unguarded AttributeError/TypeError.
    if not isinstance(result, dict):
        raise RuntimeError(
            "Anthropic models endpoint returned an unexpected payload shape "
            f"(expected object, got {type(result).__name__})."
        )
    data = result.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError(
            "Anthropic models endpoint returned an unexpected 'data' shape "
            f"(expected list, got {type(data).__name__})."
        )
    # Each entry must be an object with a non-empty string `id`. A non-string
    # id (e.g. `{"id": 123}`) would otherwise flow through and later crash
    # `", ".join(sorted(...))` in verify_model_available with a TypeError that
    # bypasses the fail-open handler. Treat any malformed entry as an
    # infrastructure error so callers fail open on a hostile/garbled response.
    ids: list[str] = []
    for m in data:
        model_id = m.get("id") if isinstance(m, dict) else None
        if not isinstance(model_id, str) or not model_id:
            raise RuntimeError(
                "Anthropic models endpoint returned a malformed model entry "
                f"(expected an object with a non-empty string 'id', got {m!r})."
            )
        ids.append(model_id)
    return ids


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
      ``model`` is not in the returned list -> raise ``RuntimeError`` listing
      the reachable ids, so a live run never spends on a dead model id.
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
        listed = ", ".join(sorted(reachable)) if reachable else "(none)"
        raise RuntimeError(
            f"Model '{model}' is not reachable with this API key. "
            f"Reachable ids: {listed}. "
            "Pass --model with one of these, or update DEFAULT_MODEL in "
            "scripts/eval/_anthropic_api.py."
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
