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
_LIMIT_NAME = re.compile(r"\b(?:usage|weekly|monthly|daily|rate|token)\s+limit", re.IGNORECASE)
_LIMIT_VERB = re.compile(r"\b(?:reached|reach|exceeded|hit)\b", re.IGNORECASE)


def _is_limit_message(message: Any) -> bool:
    if not isinstance(message, dict):
        return False
    text = extract_text(message.get("content"))
    if not 0 < len(text) <= LIMIT_MESSAGE_MAX_CHARS:
        return False
    return bool(_LIMIT_NAME.search(text) and _LIMIT_VERB.search(text))


def _termination(outcome_reason: Any, limit_message_last: bool) -> str | None:
    if outcome_reason in USAGE_LIMIT_REASONS:
        return str(outcome_reason)
    if outcome_reason is None and limit_message_last:
        return LIMIT_MESSAGE_VALUE
    return None


def parse_droid_session(path: Path, _skill_names: Any, include_subagents: bool) -> Any:
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    state = SessionState()
    meta: dict[str, Any] = {}
    seen: set[Any] = set()
    outcome_reason: Any = None
    limit_message_last = False
    for obj in records:
        kind = obj.get("type")
        if kind == "session_start":
            child = bool(obj.get("callingSessionId"))
            if child and not include_subagents:
                return None
            meta = {
                "id": obj.get("id") or path.stem,
                "cwd": obj.get("cwd"),
                "started_at": None,
                "originator": "droid",
                "thread_source": "subagent" if child else None,
            }
        elif kind == "message":
            state.timestamp(obj.get("timestamp"))
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            message = {**message, "id": message.get("id") or obj.get("id")}
            role = message.get("role")
            _claude_message(state, {"type": role, "message": message, "uuid": obj.get("id")}, seen)
            limit_message_last = _is_limit_message(message)
        elif kind == "agent_turn_outcome":
            outcome_reason = obj.get("reason")
    meta = meta or {"id": path.stem, "cwd": None, "originator": "droid", "thread_source": None}
    meta["started_at"] = state.first_ts
    terminated_by = _termination(outcome_reason, limit_message_last)
    if terminated_by:
        state.stats["terminated_by"] = terminated_by
    return state.finish(meta, DROID_EDIT_TOOLS)
