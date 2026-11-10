"""Factory Droid journal adapter for skill-doctor.

Droid keeps one JSONL file per session under
``<factory-home>/sessions/<encoded-cwd>/<id>.jsonl``. A ``session_start`` record
carries ``id`` and ``cwd``. ``message`` records carry a Claude-style
``message.content`` block list, so the Claude block handler reads them as is.
``agent_turn_outcome`` records carry a ``reason`` such as ``completed`` or
``model_usage_exhausted``.

Kept apart from ``session_json.py`` so the Droid adapter lands without editing
the shared JSON parsers.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from session_common import (
    CLAUDE_CODE_EDIT_TOOLS,
    SessionState,
    extract_text,
    iter_jsonl_records,
)
from session_json import _claude_message

DROID_EDIT_TOOLS = frozenset(CLAUDE_CODE_EDIT_TOOLS) | {"Create", "ApplyPatch"}

# Turn outcome reasons that mean the provider cut the session off for usage.
USAGE_LIMIT_REASONS = frozenset({"model_usage_exhausted"})

# A usage-limit notice is a short message. A long report that mentions a quota
# in passing is not one.
LIMIT_MESSAGE_MAX_CHARS = 400
LIMIT_MESSAGE_VALUE = "usage_limit_exceeded"
_LIMIT_NAME = re.compile(r"\b(?:usage|weekly|monthly|daily|rate|token)\s+limit\b", re.IGNORECASE)
_LIMIT_VERB = re.compile(r"\b(?:reached|exceeded)\b", re.IGNORECASE)


def _is_limit_message(message: dict[str, Any]) -> bool:
    """A short assistant notice that names a limit and says it was reached."""
    if message.get("role") != "assistant":
        return False
    text = extract_text(message.get("content"))
    if not 0 < len(text) <= LIMIT_MESSAGE_MAX_CHARS:
        return False
    return bool(_LIMIT_NAME.search(text) and _LIMIT_VERB.search(text))


def _start_meta(obj: dict[str, Any], path: Path) -> dict[str, Any]:
    child = bool(obj.get("callingSessionId"))
    return {
        "id": obj.get("id") or path.stem,
        "cwd": obj.get("cwd"),
        "started_at": None,
        "originator": "droid",
        "thread_source": "subagent" if child else None,
    }


def _apply_message(state: SessionState, obj: dict[str, Any], seen: set[Any], ending: Any) -> Any:
    state.timestamp(obj.get("timestamp"))
    message = obj.get("message")
    if not isinstance(message, dict):
        return ending
    wrapped = {"type": message.get("role"), "message": message, "uuid": obj.get("id")}
    _claude_message(state, wrapped, seen)
    # The last decisive record wins. A message with empty content, which Droid
    # writes just before a usage-exhausted outcome, decides nothing.
    if _is_limit_message(message):
        return LIMIT_MESSAGE_VALUE
    return None if message.get("content") else ending


def parse_droid_session(path: Path, _skill_names: Any, include_subagents: bool) -> Any:
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    state = SessionState()
    meta: dict[str, Any] = {}
    seen: set[Any] = set()
    ending: str | None = None
    for obj in records:
        kind = obj.get("type")
        if kind == "session_start":
            meta = _start_meta(obj, path)
            if meta["thread_source"] and not include_subagents:
                return None
        elif kind == "message":
            ending = _apply_message(state, obj, seen, ending)
        elif kind == "agent_turn_outcome":
            reason = obj.get("reason")
            ending = str(reason) if reason in USAGE_LIMIT_REASONS else None
    meta = meta or {"id": path.stem, "cwd": None, "originator": "droid", "thread_source": None}
    meta["started_at"] = state.first_ts
    if ending:
        state.terminate(ending)
    return state.finish(meta, DROID_EDIT_TOOLS)
