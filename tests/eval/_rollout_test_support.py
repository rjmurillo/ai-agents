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


def rollout_lines(
    thread_id: str,
    *,
    start: str,
    end: str,
    parent: str | None = None,
    version: str = "0.154.0",
    refusals: tuple[str, ...] = (),
    balanced: bool = True,
) -> list[str]:
    """Build a minimal rollout: meta, one turn, optional refusals, an end record."""
    meta: dict[str, object] = {"id": thread_id, "timestamp": start, "cli_version": version}
    if parent is not None:
        meta["parent_thread_id"] = parent
    lines = [
        line({"timestamp": start, "type": "session_meta", "payload": meta}),
        line({"timestamp": start, "type": "event_msg", "payload": {"type": "task_started"}}),
    ]
    for stamp in refusals:
        output = {"type": "function_call_output", "output": REFUSAL}
        lines.append(line({"timestamp": stamp, "type": "response_item", "payload": output}))
    if balanced:
        done = {"type": "task_complete"}
        lines.append(line({"timestamp": end, "type": "event_msg", "payload": done}))
    else:
        lines.append(line({"timestamp": end, "type": "token_usage_record", "payload": {}}))
    return lines


def session_start(version: str = "1.0.79-9") -> str:
    """Build a Copilot `session.start` event."""
    data = {"copilotVersion": version}
    return line({"type": "session.start", "data": data, "timestamp": "2026-08-11T14:05:25.936Z"})
