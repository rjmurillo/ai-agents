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

    search = Path(__file__).resolve().parent
    for _ in range(10):
        env_path = search / ".env"
        if env_path.exists():
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
        search = search.parent

    raise RuntimeError(
        "ANTHROPIC_API_KEY not found in environment or .env file. "
        "Set the environment variable or add it to a .env file in the repo root."
    )


def call_api(
    api_key: str,
    messages: list[dict],
    system: str = "",
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 1024,
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
    """
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
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
        error_body = e.read().decode(errors="replace")
        raise RuntimeError(
            f"Anthropic API returned HTTP {e.code}: {error_body[:500]}"
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
    except (TimeoutError, socket.timeout) as e:
        raise RuntimeError(
            "Anthropic API request timed out after 120s. "
            "The service may be slow or unreachable."
        ) from e
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Anthropic API returned invalid JSON: {e.msg} at position {e.pos}. "
            "Response may be truncated or malformed."
        ) from e

    text_parts = [block["text"] for block in result.get("content", []) if block.get("type") == "text"]
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
    prompts = data["prompts"] if isinstance(data, dict) and isinstance(data.get("prompts"), dict) else data
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
