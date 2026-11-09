"""Read-only Warp and Hermes adapters for skill-doctor.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from session_common import (
    CODE_EDIT_HINTS,
    GENERIC_EDIT_TOOLS,
    MAX_TOOL_CHARS,
    SessionState,
    assistant_tool_calls,
    detect_skill_candidates,
    looks_injected,
)
from warp_decoder import ProtobufDecodeError, decode_task

MAX_WARP_CONVERSATION_BYTES = 32 * 1024 * 1024


def parse_sqlite_timestamp(value: Any) -> Any:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_epoch_timestamp(value: Any) -> Any:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def open_warp_database(path: Any) -> Any:
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _has_table(connection: Any, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def warp_database_has_sessions(connection: Any) -> bool:
    return _has_table(connection, "agent_conversations")


def hermes_database_has_sessions(connection: Any) -> bool:
    return _has_table(connection, "sessions")


def sqlite_table_columns(connection: Any, table: Any) -> Any:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def _warp_rows(database: Any, cutoff: Any) -> Any:
    connection = None
    try:
        connection = open_warp_database(database)
        if not warp_database_has_sessions(connection):
            return []
        columns = sqlite_table_columns(connection, "agent_conversations")
        summary = "summary" if "summary" in columns else "NULL"
        return connection.execute(
            f"""
            SELECT conversation_id, conversation_data, last_modified_at, {summary} AS summary
            FROM agent_conversations WHERE last_modified_at >= ?
            ORDER BY last_modified_at DESC
            """,
            (cutoff.strftime("%Y-%m-%d %H:%M:%S"),),
        ).fetchall()
    except sqlite3.Error as exc:
        print(f"warning: could not read Warp database {database}: {exc}", file=sys.stderr)
        return []
    finally:
        if connection is not None:
            connection.close()


def find_warp_conversations(databases: Any, cutoff: Any) -> Any:
    newest: dict[str, dict[str, Any]] = {}
    scanned = 0
    for database in databases:
        rows = _warp_rows(database, cutoff)
        scanned += len(rows)
        for row in rows:
            modified_at = parse_sqlite_timestamp(row["last_modified_at"])
            if modified_at is None or modified_at < cutoff:
                continue
            record = {
                "conversation_id": row["conversation_id"],
                "conversation_data": row["conversation_data"],
                "summary": row["summary"],
                "modified_at": modified_at,
                "database": database,
                "channel": database.parent.name,
            }
            existing = newest.get(record["conversation_id"])
            if existing is None or modified_at > existing["modified_at"]:
                newest[record["conversation_id"]] = record
    return sorted(newest.values(), key=lambda row: row["modified_at"], reverse=True), scanned


def _hermes_rows(database: Any, cutoff: Any) -> Any:
    connection = None
    try:
        connection = open_warp_database(database)
        if not hermes_database_has_sessions(connection):
            return []
        if "cwd" not in sqlite_table_columns(connection, "sessions"):
            return []
        required = {"session_id", "role", "content", "tool_calls", "timestamp"}
        if not required.issubset(sqlite_table_columns(connection, "messages")):
            print(
                f"warning: skipping Hermes database {database}: incompatible messages schema",
                file=sys.stderr,
            )
            return []
        return connection.execute(
            """
            SELECT id, source, cwd, title, display_name, parent_session_id,
                   started_at, last_activity_at, ended_at
            FROM sessions WHERE COALESCE(last_activity_at, ended_at, started_at) >= ?
            ORDER BY COALESCE(last_activity_at, ended_at, started_at) DESC
            """,
            (cutoff.timestamp(),),
        ).fetchall()
    except sqlite3.Error as exc:
        print(f"warning: could not read Hermes database {database}: {exc}", file=sys.stderr)
        return []
    finally:
        if connection is not None:
            connection.close()


def find_hermes_sessions(databases: Any, cutoff: Any) -> Any:
    records = [(database, row) for database in databases for row in _hermes_rows(database, cutoff)]
    records.sort(
        key=lambda pair: (
            parse_epoch_timestamp(
                pair[1]["last_activity_at"] or pair[1]["ended_at"] or pair[1]["started_at"]
            )
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )
    return records, len(records)


def _hermes_calls(state: SessionState, raw: Any, skill_names: Any) -> None:
    try:
        calls = json.loads(raw)
    except ValueError:
        calls = []
    for name, args in assistant_tool_calls({"tool_calls": calls}):
        state.tool(name, args, hints=False)
        state.edits |= name in CODE_EDIT_HINTS or name in GENERIC_EDIT_TOOLS
        if name == "skill_view":
            _hermes_skill_view(state, args, skill_names)


def _hermes_skill_view(state: SessionState, args: str, skill_names: Any) -> None:
    try:
        payload = json.loads(args)
        name: Any = (payload or {}).get("name")
        if name in skill_names:
            state.skills.add(name)
    except (ValueError, TypeError):
        pass


def _hermes_message(state: SessionState, row: Any, skill_names: Any) -> None:
    state.timestamp(parse_epoch_timestamp(row["timestamp"]))
    role, content = row["role"], row["content"] or ""
    if role == "user" and content.strip():
        if state.text("user", content):
            state.stats["user_turns"] += 1
    elif role == "assistant":
        state.stats["assistant_turns"] += 1
        if content.strip() and not looks_injected(content):
            state.skills |= detect_skill_candidates(content) & set(skill_names)
            state.append("assistant", content)
        if row["tool_calls"]:
            _hermes_calls(state, row["tool_calls"], skill_names)
    elif role == "tool" and content.strip():
        # Hermes used a narrower error window than the JSON journal adapters.
        lowered = content[:200].lower()
        state.stats["error_outputs"] += int("error" in lowered or "traceback" in lowered)
        state.append("tool_output", content, MAX_TOOL_CHARS)


def parse_hermes_session(
    connection: Any,
    session_row: Any,
    skill_names: Any,
    include_subagents: bool,
) -> Any:
    if session_row["parent_session_id"] and not include_subagents:
        return None
    meta = {
        "id": session_row["id"],
        "source": session_row["source"] or "cli",
        "cwd": session_row["cwd"],
        "title": session_row["title"] or session_row["display_name"],
    }
    state = SessionState()
    state.skills = detect_skill_candidates(session_row["cwd"] or "")
    rows = connection.execute(
        """SELECT role, content, tool_calls, timestamp FROM messages
        WHERE session_id = ? ORDER BY timestamp""",
        (session_row["id"],),
    ).fetchall()
    for row in rows:
        _hermes_message(state, row, skill_names)
    if state.stats["assistant_turns"] < 1 or state.stats["tool_calls"] < 1:
        return None
    first = state.first_ts or parse_epoch_timestamp(session_row["started_at"])
    last = (
        state.last_ts
        or parse_epoch_timestamp(session_row["last_activity_at"])
        or parse_epoch_timestamp(session_row["ended_at"])
        or first
    )
    if first is not None:
        meta["started_at"] = first.isoformat()
    meta["timestamp"] = (last or datetime.now(tz=timezone.utc)).isoformat()
    state.first_ts = first.isoformat() if first is not None else None
    state.last_ts = last.isoformat() if last is not None else None
    state.skills.intersection_update(skill_names)
    state.stats["skills"] = sorted(state.skills)
    return state.finish(meta)


def load_warp_conversation_data(record: Any) -> Any:
    connection = open_warp_database(record["database"])
    try:
        tasks = connection.execute(
            "SELECT task FROM agent_tasks WHERE conversation_id = ? ORDER BY id",
            (record["conversation_id"],),
        ).fetchall()
        columns = sqlite_table_columns(connection, "ai_queries")
        queries = []
        if {"conversation_id", "start_ts"}.issubset(columns):
            cwd = "working_directory" if "working_directory" in columns else "NULL"
            queries = connection.execute(
                f"""SELECT start_ts, {cwd} AS working_directory FROM ai_queries
                WHERE conversation_id = ? ORDER BY start_ts""",
                (record["conversation_id"],),
            ).fetchall()
    finally:
        connection.close()
    blobs = [bytes(row["task"]) for row in tasks]
    total_bytes = sum(len(blob) for blob in blobs)
    if total_bytes > MAX_WARP_CONVERSATION_BYTES:
        raise ProtobufDecodeError(
            f"conversation task snapshot is {total_bytes} bytes "
            f"(limit {MAX_WARP_CONVERSATION_BYTES})"
        )
    first_query_at = working_directory = None
    for row in queries:
        first_query_at = first_query_at or parse_sqlite_timestamp(row["start_ts"])
        working_directory = working_directory or row["working_directory"]
    return blobs, first_query_at, working_directory


def skill_name_from_reference(reference: Any, skill_names: Any) -> Any:
    if not reference:
        return None
    candidates = [reference.get("name"), reference.get("bundled_skill_id")]
    path = reference.get("path")
    if path:
        skill_path = Path(path)
        candidates.extend((skill_path.parent.name, skill_path.stem))
    return next((name for name in candidates if name in skill_names), None)


def _warp_skill(state: SessionState, reference: Any, skill_names: Any) -> None:
    name = skill_name_from_reference(reference, skill_names)
    if name:
        state.skills.add(name)
    if reference:
        state.append("skill", json.dumps(reference, ensure_ascii=False), MAX_TOOL_CHARS)


def _warp_user(state: SessionState, message: Any, cwd: Any) -> Any:
    text = message.get("text", "")
    if state.text("user", text):
        state.stats["user_turns"] += 1
    return cwd or message.get("cwd")


def _warp_message(state: SessionState, message: Any, cwd: Any, skill_names: Any) -> Any:
    state.timestamp(message.get("timestamp"))
    kind = message["kind"]
    if kind == "user_query":
        cwd = _warp_user(state, message, cwd)
    elif kind == "invoke_skill":
        _warp_skill(state, message.get("skill"), skill_names)
        cwd = _warp_user(state, message.get("user_query") or {}, cwd)
    elif kind == "agent_output":
        text = message.get("text", "")
        if text:
            state.stats["assistant_turns"] += 1
            state.append("assistant", text)
    elif kind == "tool_call":
        name, payload = message.get("name", "unknown"), message.get("payload", "")
        # Warp skill detection uses explicit references, not arbitrary tool payloads.
        state.tool(name, payload, hints=False, skill_candidates=False)
        state.edits |= name == "apply_file_diffs"
        _warp_skill(state, message.get("skill"), skill_names)
    elif kind == "tool_call_result":
        state.output(message.get("payload", ""))
        cwd = cwd or message.get("cwd")
    return cwd


def _json_metadata(value: Any) -> Any:
    try:
        return json.loads(value or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _warp_messages(tasks: Any) -> list[Any]:
    messages: list[Any] = []
    for task in tasks:
        for message in task["messages"]:
            message["_sequence"] = len(messages)
            messages.append(message)
    messages.sort(
        key=lambda message: (
            message.get("order_key") is None,
            message.get("order_key") or (0, 0),
            message["_sequence"],
        )
    )
    return messages


def parse_warp_conversation(record: Any, skill_names: Any, include_subagents: Any) -> Any:
    conversation = _json_metadata(record["conversation_data"])
    child = bool(conversation.get("parent_agent_id") or conversation.get("parent_conversation_id"))
    if child and not include_subagents:
        return None
    summary = _json_metadata(record["summary"])
    try:
        blobs, first_query_at, query_cwd = load_warp_conversation_data(record)
        tasks = [decode_task(blob) for blob in blobs]
    except (OSError, sqlite3.Error, ProtobufDecodeError) as exc:
        print(
            f"warning: could not decode Warp conversation "
            f"{record['conversation_id']} from {record['channel']}: {exc}",
            file=sys.stderr,
        )
        return None
    state = SessionState(bounded=False)
    cwd = summary.get("initial_working_directory") or query_cwd
    for message in _warp_messages(tasks):
        cwd = _warp_message(state, message, cwd, skill_names)
    meta = {
        "id": record["conversation_id"],
        "cwd": cwd,
        "started_at": state.first_ts or (first_query_at.isoformat() if first_query_at else None),
        "originator": "warp",
        "thread_source": "subagent" if child else None,
        "channel": record["channel"],
    }
    return state.finish(meta)
