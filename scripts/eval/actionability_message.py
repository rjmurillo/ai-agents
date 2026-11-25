"""The model input of the actionability predict step: prompt, limits, delimiters, and its hash.

Split out of ``actionability_predict.py``, which re-exports every name here. Each untrusted
field (path, comment, replies) is wrapped in delimiters that carry a random per-call token,
so text inside a comment cannot close its own delimiter (CWE-1427, prompt injection).
``input_sha256`` hashes what the model is sent, so a resumed run can tell when a row changed.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from typing import Any

from scripts.eval.actionability_io import REPO_ROOT, sha256_hex

PROMPT_PATH = REPO_ROOT / "evals" / "comment-actionability" / "prompt-v1.md"

# Spec Call contract limits.
MAX_BODY_CHARS = 4000
MAX_REPLIES = 3
MAX_REPLY_CHARS = 500
MAX_TOKEN_ATTEMPTS = 8


def load_prompt() -> tuple[str, str]:
    """Return the system prompt text and the SHA-256 of the prompt file bytes."""
    raw = PROMPT_PATH.read_bytes()
    return raw.decode("utf-8").strip(), sha256_hex(raw)


def _new_token() -> str:
    return secrets.token_hex(8)


def _wrap(name: str, token: str, text: str) -> str:
    return f"<{name}-{token}>\n{text}\n</{name}-{token}>"


def _sent_fields(row: dict[str, Any]) -> tuple[str, str, list[str]]:
    """The path, body, and replies of ``row`` as the model sees them, after truncation."""
    path = row.get("path") or ""
    body = (row.get("body") or "")[:MAX_BODY_CHARS]
    replies = [r[:MAX_REPLY_CHARS] for r in (row.get("thread_replies") or [])[:MAX_REPLIES]]
    return path, body, replies


def input_sha256(row: dict[str, Any]) -> str:
    """SHA-256 of what the model is sent for ``row``, minus the per-call delimiter token.

    A resumed run reuses a carried verdict only when this still matches, so an edited body or
    reply in the corpus is predicted again instead of keeping the verdict for the old text.
    """
    payload = json.dumps(_sent_fields(row), ensure_ascii=False).encode("utf-8")
    return sha256_hex(payload)


def build_user_message(row: dict[str, Any], token_factory: Callable[[], str] = _new_token) -> str:
    """Build the model input. The heuristic score is logged, never sent.

    Each untrusted field (path, comment, replies) is wrapped in tags that carry a
    per-call random token, so no text a commenter writes can close its own
    delimiter. The token is re-drawn if it appears anywhere in the data.
    """
    path, body, replies = _sent_fields(row)
    fields = [path, body, *replies]
    for _ in range(MAX_TOKEN_ATTEMPTS):
        token = token_factory()
        if not any(token in field for field in fields):
            break
    else:
        raise ValueError("could not pick a delimiter token that is absent from the data")
    parts = [f"Delimiter token: {token}", "", _wrap("path", token, path)]
    parts += ["", _wrap("comment", token, body)]
    for reply in replies:
        parts += ["", _wrap("reply", token, reply)]
    return "\n".join(parts)
