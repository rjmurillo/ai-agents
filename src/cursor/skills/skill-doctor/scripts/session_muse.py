"""Muse session journal adapter for skill-doctor.

Muse stores one event-sourced journal per session at
``<muse-home>/sessions/YYYY/MM/DD/<session-id>/session.jsonl``. Each line is
a record with a ``payload_type`` and a ``payload``; the first line may wrap
child records as JSON strings under ``children[].record_json``.

The journal retains user prompts, tool names, and tool outcomes. It does not
retain assistant prose, tool arguments, or tool output text, so transcripts
built from it contain user turns and tool names only. ``assistant_turns``
counts distinct tool-batch runs: one run is one model response that issued
tools. A session with no tool calls is not scoreable by the collector.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from session_common import GENERIC_EDIT_TOOLS, SessionState, _recent_files, iter_jsonl_records


def find_muse_session_files(muse_home: Path, cutoff: datetime) -> Any:
    return _recent_files((muse_home / "sessions").glob("*/*/*/*/session.jsonl"), cutoff)


def _muse_timestamp(value: Any) -> str | None:
    """Muse records ``recorded_at`` as epoch microseconds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1_000_000, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _muse_records(path: Path) -> Any:
    """Yield journal records, unwrapping the leading transaction record."""
    for obj in iter_jsonl_records(path):
        if obj.get("payload_type"):
            yield obj
        for child in obj.get("children") or []:
            if not isinstance(child, dict):
                continue
            raw = child.get("record_json")
            if not isinstance(raw, str):
                continue
            try:
                record = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(record, dict) and record.get("payload_type"):
                yield record


def _intent_text(payload: Any) -> str:
    parts = []
    for message in payload.get("model_messages") or []:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
            continue
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(parts)


def _record_cwd(payload: Any) -> Any:
    record = payload.get("record")
    if not isinstance(record, dict):
        return None
    return record.get("workspace_root") or record.get("cwd")


def _muse_event(
    state: SessionState, meta: dict[str, Any], kind: Any, payload: Any, runs: set[Any]
) -> None:
    if kind in (
        "runtime.session.metadata",
        "runtime.session.route_facts",
        "session.workspace_branch.observed",
    ):
        meta["cwd"] = meta["cwd"] or _record_cwd(payload)
        record = payload.get("record") or {}
        build = record.get("build") or {}
        if isinstance(build, dict) and build.get("semver"):
            meta["cli_version"] = meta.get("cli_version") or build["semver"]
    elif kind == "runtime.user_intent.accepted":
        if state.text("user", _intent_text(payload)):
            state.stats["user_turns"] += 1
    elif kind == "tool_batch.effect.started":
        record = payload.get("record") or {}
        if payload.get("run_id") is not None:
            runs.add(payload["run_id"])
        name = str(record.get("tool_name") or "unknown")
        state.tool(name, f"call_id {record.get('call_id') or ''}".strip())
    elif kind == "tool_batch.effect.terminal":
        record = payload.get("record") or {}
        outcome = record.get("outcome") or {}
        failed = isinstance(outcome, dict) and outcome.get("kind") == "failed"
        label = outcome.get("kind") if isinstance(outcome, dict) else "unknown"
        state.output(f"tool outcome: {label}", failed)


def parse_muse_session(path: Path, _skill_names: Any, _include_subagents: bool) -> Any:
    try:
        records = list(_muse_records(path))
    except OSError:
        return None
    state = SessionState()
    meta: dict[str, Any] = {
        "id": path.parent.name,
        "cwd": None,
        "started_at": None,
        "originator": "muse",
        "thread_source": None,
    }
    runs: set[Any] = set()
    for obj in records:
        state.timestamp(_muse_timestamp(obj.get("recorded_at")))
        payload = obj.get("payload")
        if isinstance(payload, dict):
            _muse_event(state, meta, obj.get("payload_type"), payload, runs)
    state.stats["assistant_turns"] = len(runs)
    meta["started_at"] = state.first_ts
    result = state.finish(meta, GENERIC_EDIT_TOOLS)
    return result if result[2] else None
