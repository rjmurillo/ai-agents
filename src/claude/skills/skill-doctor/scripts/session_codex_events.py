"""Codex event-record helpers for skill-doctor: completion state and event-only corpus rows.

Split from ``session_json.py`` to keep that module under the file-size ceiling.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

from typing import Any

from session_common import SessionState, looks_injected


def _error_reason(info: Any) -> str:
    if isinstance(info, str) and info:
        return info
    if isinstance(info, dict) and info:
        return str(next(iter(info)))
    return "error"


def _completion(state: SessionState, payload: dict[str, Any]) -> None:
    """`task_complete.error.codex_error_info` marks a provider cutoff; a clean one resumes."""
    error = payload.get("error")
    if not error:
        state.resume()
        return
    if not isinstance(error, dict):
        state.terminate("error", str(error))
        return
    state.terminate(_error_reason(error.get("codex_error_info")), str(error.get("message") or ""))


def codex_event(
    state: SessionState,
    payload: dict[str, Any],
    events: dict[str, int],
    pending: dict[str, list[tuple[Any, str, Any]]],
    stamp: tuple[Any, Any],
) -> None:
    event_roles = {"user_message": "user", "agent_message": "assistant"}
    if payload.get("type") in event_roles:
        role = event_roles[payload["type"]]
        events[role] += 1
        text = payload.get("message")
        if isinstance(text, str) and text.strip() and not (role == "user" and looks_injected(text)):
            pending[role].append((stamp[0], text, stamp[1]))
    elif payload.get("type") == "task_complete":
        _completion(state, payload)


def codex_event_only_rows(capture: Any, pending: dict[str, list[tuple[Any, str, Any]]]) -> None:
    """Export event text for a role that has no `response_item` text, so no turn lands twice."""
    if capture is None:
        return
    added = False
    for role, rows in pending.items():
        if any(row["role"] == role for row in capture.rows):
            continue
        for line, text, ts in rows:
            capture.record_at(line, role, text, ts)
            added = True
    if added:
        capture.rows.sort(key=lambda row: row["line"] if isinstance(row["line"], int) else 0)
