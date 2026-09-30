"""Synthetic rollout and event builders for the recorded-capture tests (issue #5423)."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "harness_capability"
ROLLOUTS = FIXTURES / "codex-0.154.0-rollouts"
REFUSAL = "collab spawn failed: agent thread limit reached"


def line(record: dict[str, object]) -> str:
    """Serialize one JSONL record."""
    return json.dumps(record)


def _refusal_lines(stamps: tuple[str, ...]) -> list[str]:
    output = {"type": "function_call_output", "output": REFUSAL}
    return [line({"timestamp": s, "type": "response_item", "payload": output}) for s in stamps]


def rollout_lines(
    thread_id: str,
    *,
    start: str,
    end: str,
    parent: str | None = None,
    version: str = "0.154.0",
    refusals: tuple[str, ...] = (),
    balanced: bool = True,
    turns: tuple[tuple[str, str], ...] | None = None,
) -> list[str]:
    """Build a minimal rollout: meta, turns, optional refusals, an end record.

    `turns` lists (started, completed) spans; the default is one span from
    `start` to `end`. `balanced=False` leaves the last span unclosed.
    """
    meta: dict[str, object] = {"id": thread_id, "timestamp": start, "cli_version": version}
    if parent is not None:
        meta["parent_thread_id"] = parent
    lines = [line({"timestamp": start, "type": "session_meta", "payload": meta})]
    spans = turns if turns is not None else ((start, end),)
    for index, (opened, closed) in enumerate(spans):
        started = {"type": "task_started"}
        lines.append(line({"timestamp": opened, "type": "event_msg", "payload": started}))
        if index == len(spans) - 1:
            lines.extend(_refusal_lines(refusals))
        if balanced or index < len(spans) - 1:
            done = {"type": "task_complete"}
            lines.append(line({"timestamp": closed, "type": "event_msg", "payload": done}))
    if not balanced:
        lines.append(line({"timestamp": end, "type": "token_usage_record", "payload": {}}))
    return lines


def session_start(version: str = "1.0.79-9") -> str:
    """Build a Copilot `session.start` event."""
    data = {"copilotVersion": version}
    return line({"type": "session.start", "data": data, "timestamp": "2026-08-11T14:05:25.936Z"})
