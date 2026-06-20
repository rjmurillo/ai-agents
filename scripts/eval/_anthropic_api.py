"""Shared Anthropic API utilities for evaluation scripts.

This module provides common functions for loading API keys, calling the
Anthropic Messages API, and loading custom prompt JSON files. Used by
eval-agents.py and eval-knowledge-integration.py.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


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


def call_api(
    api_key: str,
    messages: list[dict[str, str]],
    system: str = "",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1024,
    temperature: float = 0.0,
    provider: str | None = None,
) -> str:
    """Call the Anthropic Messages API.

    Args:
        api_key: The Anthropic API key.
        messages: List of message dicts with 'role' and 'content' keys.
        system: Optional system prompt.
        model: Model identifier to use.
        max_tokens: Maximum tokens in the response.

    Returns:
        The assistant's text response.

    Raises:
        RuntimeError: If the API returns an HTTP error, network failure,
            timeout, or invalid JSON response. Original exception is chained
            via __cause__.

        provider: Optional transport selector. None falls back to the
            EVAL_PROVIDER env var. The default (None / "anthropic") uses this
            urllib path unchanged; any other value routes through
            `_providers.resolve_provider` (openai, github, anthropic-sdk).
            `api_key` is ignored for non-Anthropic providers.
    """
    selected = provider if provider is not None else os.environ.get("EVAL_PROVIDER")
    if selected is not None:
        from _providers import is_default_anthropic, resolve_provider

        if not is_default_anthropic(selected):
            return resolve_provider(selected).complete(
                messages=messages,
                system=system,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
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
        raise RuntimeError(
            f"Anthropic API returned HTTP {e.code}: {sanitized}"
        ) from e
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
