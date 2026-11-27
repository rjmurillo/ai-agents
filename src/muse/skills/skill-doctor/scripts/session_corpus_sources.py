"""Corpus-only adapters for skill-doctor: T3 Code threads and Gemini antigravity.

Both sources hold conversation text with no tool calls, so they never reach
scoring. ``collect_corpus_sources`` runs only when ``--export-corpus`` is set.
A missing source is skipped, as for every other harness, unless the user named
it with ``--harness``. Neither source records a working directory, so the
repository filter admits them only under ``--all-conversations``.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import itertools
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from session_common import (
    SessionState,
    _recent_files,
    extract_text,
    iter_jsonl_records,
    parse_session_timestamp,
    record_collection_issue,
)
from session_corpus import current_capture
from session_databases import sqlite_table_columns

T3_THREADS = "orchestration_v2_projection_threads"
T3_MESSAGES = "orchestration_v2_projection_messages"
T3_REQUIRED = {
    T3_THREADS: {"thread_id", "title"},
    T3_MESSAGES: {"message_id", "thread_id", "role", "created_at", "payload_json"},
}
T3_QUERY = (
    "SELECT message_id, thread_id, role, created_at, payload_json "
    f"FROM {T3_MESSAGES} ORDER BY thread_id, created_at"
)
GEMINI_ROLES = {"PLANNER_RESPONSE": "assistant", "USER_INPUT": "user"}
GEMINI_LOG = ".system_generated/logs/transcript_full.jsonl"


def t3_database(home: Path) -> Path:
    return home / "userdata" / "statev2.sqlite"


def open_t3_database(path: Path) -> sqlite3.Connection:
    """Open read-only. Not immutable: a running T3 server keeps writing its WAL."""
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=2)
    connection.execute("PRAGMA query_only = ON")
    return connection


def t3_schema_matches(connection: sqlite3.Connection) -> bool:
    return all(
        required <= sqlite_table_columns(connection, table)
        for table, required in T3_REQUIRED.items()
    )


def t3_message_text(payload: Any) -> str:
    """Read `text`, else `content`; either may be a string or a list of blocks."""
    if not isinstance(payload, dict):
        return ""
    value = payload.get("text") or payload.get("content") or ""
    return value if isinstance(value, str) else extract_text(value)


def _decode_payload(raw: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        record_collection_issue("malformed_records")
        return None


def parse_t3_thread(thread_id: str, title: Any, rows: list[Any], cutoff: datetime) -> Any:
    """Build a parsed-session tuple from one thread's message rows, or None."""
    capture = current_capture()
    state = SessionState(bounded=False)
    meta = {"id": thread_id, "cwd": None, "originator": "t3", "title": title}
    for message_id, _thread, role, created_at, raw in rows:
        when = parse_session_timestamp(created_at)
        if role not in ("user", "assistant") or when is None or when < cutoff:
            continue
        text = t3_message_text(_decode_payload(raw))
        state.timestamp(created_at)
        if capture is not None:
            capture.line = message_id
        if role == "user":
            state.text(role, text)
        elif text:
            state.append(role, text)
    meta["started_at"] = state.first_ts
    return None if state.last_ts is None else state.finish(meta)


def collect_t3(collection: Any, home: Path, cutoff: datetime) -> bool:
    """Feed every in-window T3 thread to `collection.add`. False when no database."""
    path = t3_database(home)
    if not path.is_file():
        return False
    collection.sources["t3"] = {"home": str(home), "records_in_window": 0}
    try:
        connection = open_t3_database(path)
    except (OSError, sqlite3.Error):
        record_collection_issue("database_failures")
        return True
    try:
        if not t3_schema_matches(connection):
            record_collection_issue("schema_mismatch")
            return True
        titles = dict(connection.execute(f"SELECT thread_id, title FROM {T3_THREADS}"))
        grouped = itertools.groupby(connection.execute(T3_QUERY), key=lambda row: row[1])
        for thread_id, rows in grouped:
            parsed = parse_t3_thread(thread_id, titles.get(thread_id), list(rows), cutoff)
            collection.scanned += 1
            if parsed is not None:
                collection.sources["t3"]["records_in_window"] += 1
                collection.add("t3", parsed, f"t3:{thread_id}", parsed[0]["started_at"])
    except sqlite3.Error:
        record_collection_issue("database_failures")
    finally:
        connection.close()
    return True


def find_gemini_transcripts(home: Path, cutoff: datetime) -> list[tuple[datetime, Path]]:
    return _recent_files((home / "brain").glob(f"*/{GEMINI_LOG}"), cutoff)


def parse_gemini_session(path: Path) -> Any:
    """Read `PLANNER_RESPONSE` and `USER_INPUT` records whose content is a string."""
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    state = SessionState(bounded=False)
    for record in records:
        role = GEMINI_ROLES.get(record.get("type"))
        content = record.get("content")
        if role is None or not isinstance(content, str):
            continue
        state.timestamp(record.get("timestamp") or record.get("created_at"))
        if role == "user":
            state.text(role, content)
        else:
            state.append(role, content)
    meta = {"id": path.parents[2].name, "cwd": None, "originator": "gemini"}
    meta["started_at"] = state.first_ts
    return state.finish(meta)


def collect_gemini(collection: Any, home: Path, cutoff: datetime) -> bool:
    """Feed every in-window Gemini transcript to `collection.add`. False when no brain dir."""
    if not (home / "brain").is_dir():
        return False
    paths = find_gemini_transcripts(home, cutoff)
    collection.sources["gemini"] = {"home": str(home), "records_in_window": len(paths)}
    collection.scanned += len(paths)
    for mtime, path in paths:
        collection.add("gemini", parse_gemini_session(path), str(path), mtime.isoformat())
    return True


def collect_corpus_sources(collection: Any, cutoff: datetime) -> None:
    """Read the corpus-only sources the harness selection allows."""
    args = collection.args
    adapters = (
        ("t3", collect_t3, Path(args.t3_home).expanduser()),
        ("gemini", collect_gemini, Path(args.gemini_home).expanduser()),
    )
    for name, adapter, home in adapters:
        if not collection.requested(name):
            continue
        if not adapter(collection, home, cutoff) and args.harness == name:
            print(f"error: {name} source not found under {home}", file=sys.stderr)
            sys.exit(2)
