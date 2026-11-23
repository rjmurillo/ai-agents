"""Muse session journal adapter for skill-doctor.

Muse stores one event-sourced journal per session at
``<muse-home>/sessions/YYYY/MM/DD/<session-id>/session.jsonl``. Each line is
a record with a ``payload_type`` and a ``payload``; the first line may wrap
child records as JSON strings under ``children[].record_json``.

Run records (``runtime.session`` with ``kind: run``) carry assistant prose
(``assistant_message_committed``), tool calls with JSON arguments
(``assistant_tool_calls_committed``), tool outputs
(``tool_result_batch_committed``), and per-response completion
(``model_completed``). Tool calls also appear as
``tool_batch.effect.started`` / ``tool_batch.effect.terminal`` records with
names and outcomes; the parser emits each call once, enriched with arguments
when a run record names the same ``call_id``, so journals without run records
still yield tool names. ``assistant_turns`` counts distinct run ids. A session
is scoreable only when it has at least one assistant turn and at least one
tool call. ``call_id`` values that are not strings or integers are malformed
and counted as such; their records never abort parsing of the session.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from session_common import (
    GENERIC_EDIT_TOOLS,
    SessionState,
    _recent_files,
    iter_jsonl_records,
    record_collection_issue,
)


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
                record_collection_issue("malformed_records")
                continue
            if isinstance(record, dict) and record.get("payload_type"):
                yield record
            else:
                record_collection_issue("malformed_records")


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


def _record(payload: Any) -> dict[str, Any]:
    record = payload.get("record")
    if isinstance(record, dict):
        return record
    if record is not None:
        record_collection_issue("malformed_records")
    return {}


def _record_cwd(payload: Any) -> Any:
    record = _record(payload)
    return record.get("workspace_root") or record.get("cwd")


def _valid_call_id(value: Any) -> bool:
    """Call ids are strings; tolerate integers as hashable identifiers."""
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def _run_calls(records: list[dict[str, Any]]) -> dict[Any, str]:
    """Map tool ``call_id`` to ``name args`` text from run commit records.

    Invalid ids are skipped here; the emission site counts the record once.
    """
    calls: dict[Any, str] = {}
    for obj in records:
        if obj.get("payload_type") != "runtime.session":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict) or payload.get("kind") != "run":
            continue
        event = payload.get("event")
        if not isinstance(event, dict) or event.get("kind") != "assistant_tool_calls_committed":
            continue
        for call in event.get("tool_calls") or []:
            if not isinstance(call, dict) or not _valid_call_id(call.get("call_id")):
                continue
            name = str(call.get("name") or "unknown")
            args = call.get("args")
            text = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
            calls.setdefault(call.get("call_id"), f"{name} {text}")
    return calls


def _started_call_ids(records: list[dict[str, Any]]) -> set[Any]:
    """Collect ``call_id`` values emitted through batch started records."""
    seen: set[Any] = set()
    for obj in records:
        if obj.get("payload_type") != "tool_batch.effect.started":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        call_id = _record(payload).get("call_id")
        if _valid_call_id(call_id):
            seen.add(call_id)
    return seen


def _muse_run_event(state: SessionState, payload: dict[str, Any], runs: set[Any]) -> None:
    """Map one ``kind: run`` event: prose, completion, outputs.

    Tool calls are emitted at their batch started records (enriched with
    arguments) or, when no started record names the call, here.
    """
    if payload.get("kind") != "run":
        return
    event = payload.get("event")
    if not isinstance(event, dict):
        return
    kind = event.get("kind")
    if kind == "model_completed":
        if payload.get("run_id") is not None:
            runs.add(payload["run_id"])
    elif kind == "assistant_message_committed":
        state.text("assistant", event.get("text") or "")
    elif kind == "tool_result_batch_committed":
        for result in event.get("results") or []:
            if isinstance(result, dict) and result.get("text"):
                state.output(str(result["text"]))


def _emit_commit_only_call(
    state: SessionState,
    payload: dict[str, Any],
    runs: set[Any],
    calls: dict[Any, str],
    started_ids: set[Any],
) -> None:
    """Emit run-commit calls that no batch started record names, counting the turn."""
    event = payload.get("event")
    if not isinstance(event, dict) or event.get("kind") != "assistant_tool_calls_committed":
        return
    for call in event.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        call_id = call.get("call_id")
        if not _valid_call_id(call_id):
            record_collection_issue("malformed_records")
            continue
        if call_id in started_ids or call_id not in calls:
            continue
        state.tool(str(call.get("name") or "unknown"), calls[call_id])
        if payload.get("run_id") is not None:
            runs.add(payload["run_id"])


def _muse_event(
    state: SessionState,
    meta: dict[str, Any],
    kind: Any,
    payload: Any,
    runs: set[Any],
    calls: dict[Any, str],
    started_ids: set[Any],
) -> None:
    if kind in (
        "runtime.session.metadata",
        "runtime.session.route_facts",
        "session.workspace_branch.observed",
    ):
        meta["cwd"] = meta["cwd"] or _record_cwd(payload)
        record = _record(payload)
        build = record.get("build") or {}
        if isinstance(build, dict) and build.get("semver"):
            meta["cli_version"] = meta.get("cli_version") or build["semver"]
    elif kind == "runtime.user_intent.accepted":
        if state.text("user", _intent_text(payload)):
            state.stats["user_turns"] += 1
    elif kind == "runtime.session" and isinstance(payload, dict):
        _muse_run_event(state, payload, runs)
        _emit_commit_only_call(state, payload, runs, calls, started_ids)
    elif kind == "tool_batch.effect.started":
        record = _record(payload)
        if payload.get("run_id") is not None:
            runs.add(payload["run_id"])
        name = str(record.get("tool_name") or "unknown")
        call_id = record.get("call_id")
        if not _valid_call_id(call_id):
            record_collection_issue("malformed_records")
            state.tool(name, "call_id invalid")
        else:
            state.tool(name, calls.get(call_id, f"call_id {call_id}".strip()))
    elif kind == "tool_batch.effect.terminal":
        record = _record(payload)
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
    calls = _run_calls(records)
    started_ids = _started_call_ids(records)
    for obj in records:
        state.timestamp(_muse_timestamp(obj.get("recorded_at")))
        payload = obj.get("payload")
        if isinstance(payload, dict):
            _muse_event(state, meta, obj.get("payload_type"), payload, runs, calls, started_ids)
    state.stats["assistant_turns"] = len(runs)
    meta["started_at"] = state.first_ts
    result = state.finish(meta, GENERIC_EDIT_TOOLS)
    return result if result[2] else None
