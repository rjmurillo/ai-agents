"""JSON journal adapters for skill-doctor.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from session_common import (
    CLAUDE_CODE_EDIT_TOOLS,
    GENERIC_EDIT_TOOLS,
    SessionState,
    assistant_tool_calls,
    detect_skills_from_entries,
    extract_text,
    iter_jsonl_records,
)


def _blocks(content: Any) -> list[Any]:
    return content if isinstance(content, list) else [{"type": "text", "text": content}]


def _arguments(args: Any) -> str:
    return args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)


def _claude_meta(meta: Any, obj: Any, ts: Any) -> Any:
    if not meta and obj.get("sessionId"):
        session_id, agent_id = obj["sessionId"], obj.get("agentId")
        return {
            "id": f"{session_id}-{agent_id}" if agent_id else session_id,
            "cwd": obj.get("cwd"),
            "started_at": ts,
            "originator": "claude-code",
            "thread_source": "subagent" if obj.get("isSidechain") else None,
            "cli_version": obj.get("version"),
            "entrypoint": obj.get("entrypoint"),
        }
    if not meta:
        return meta
    for key, value in (
        ("cwd", obj.get("cwd")),
        ("started_at", ts),
        ("cli_version", obj.get("version")),
        ("entrypoint", obj.get("entrypoint")),
    ):
        meta[key] = meta.get(key) or value
    agent_id = obj.get("agentId")
    if agent_id and not meta["id"].endswith(f"-{agent_id}"):
        meta["id"] = f"{obj.get('sessionId') or meta['id']}-{agent_id}"
    return meta


def _claude_block(state: SessionState, block: Any, role: str) -> bool:
    if not isinstance(block, dict):
        return False
    kind = block.get("type")
    if kind == "text":
        text = block.get("text")
        if isinstance(text, str) and role in ("user", "assistant"):
            return state.text(role, text) and role == "user"
    elif kind == "tool_use":
        name, args = str(block.get("name") or "unknown"), block.get("input") or {}
        state.tool(name, _arguments(args))
        if name == "Skill" and isinstance(args, dict) and args.get("skill"):
            state.skills.add(args["skill"])
    elif kind == "tool_result":
        state.output(extract_text(block.get("content")), bool(block.get("is_error")))
    return False


def _claude_message(state: SessionState, obj: Any, seen: set[Any]) -> None:
    kind, message = obj.get("type"), obj.get("message")
    if kind not in ("user", "assistant") or not isinstance(message, dict):
        return
    role = message.get("role") or kind
    if role == "assistant":
        message_id = message.get("id") or obj.get("uuid")
        if message_id and message_id not in seen:
            seen.add(message_id)
            state.stats["assistant_turns"] += 1
    # Evaluate every block, even after finding user text.
    user_blocks = [_claude_block(state, block, role) for block in _blocks(message.get("content"))]
    if role == "user" and any(user_blocks):
        state.stats["user_turns"] += 1


def parse_claude_session(path: Path, _skill_names: Any, include_subagents: bool) -> Any:
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    state = SessionState()
    meta: dict[str, Any] = {}
    seen: set[Any] = set()
    sidechain = False
    for obj in records:
        state.timestamp(obj.get("timestamp"))
        if obj.get("isSidechain"):
            sidechain = True
            if not include_subagents:
                return None
        meta = _claude_meta(meta, obj, obj.get("timestamp"))
        _claude_message(state, obj, seen)
    if not meta:
        meta = {
            "id": path.stem,
            "cwd": None,
            "started_at": state.first_ts,
            "originator": "claude-code",
            "thread_source": None,
        }
    if sidechain:
        meta["thread_source"] = "subagent"
    return state.finish(meta, CLAUDE_CODE_EDIT_TOOLS)


def _codex_response(state: SessionState, payload: Any) -> None:
    kind = payload.get("type")
    if kind == "message":
        role = payload.get("role")
        text = extract_text(payload.get("content"))
        if role == "user":
            state.text(role, text)
        elif role == "assistant" and text:
            state.append(role, text)
    elif kind in ("function_call", "custom_tool_call", "local_shell_call"):
        args = payload.get("arguments") or payload.get("input") or ""
        state.tool(payload.get("name") or kind, args if isinstance(args, str) else json.dumps(args))
    elif kind in ("function_call_output", "custom_tool_call_output"):
        out = payload.get("output") or ""
        state.output(out if isinstance(out, str) else json.dumps(out))


def parse_codex_session(path: Path, _skill_names: Any, include_subagents: bool) -> Any:
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    state, meta = SessionState(), {}
    for obj in records:
        payload = obj.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        state.timestamp(obj.get("timestamp"))
        kind = obj.get("type")
        if kind == "session_meta":
            meta = {
                "id": payload.get("id") or payload.get("session_id") or path.stem,
                "cwd": payload.get("cwd"),
                "started_at": payload.get("timestamp"),
                "originator": payload.get("originator"),
                "thread_source": payload.get("thread_source"),
                "cli_version": payload.get("cli_version"),
            }
            source = payload.get("source")
            child = payload.get("thread_source") == "subagent" or (
                isinstance(source, dict) and "subagent" in source
            )
            if child and not include_subagents:
                return None
        elif kind == "event_msg":
            counter = {"user_message": "user_turns", "agent_message": "assistant_turns"}
            if payload.get("type") in counter:
                state.stats[counter[payload["type"]]] += 1
        elif kind == "response_item":
            _codex_response(state, payload)
    return state.finish(meta or {"id": path.stem, "cwd": None, "started_at": state.first_ts})


def _pi_output(state: SessionState, message: Any, blocks: Any) -> None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = block.get("text") or ""
        if isinstance(text, str) and text:
            state.output(text, bool(message.get("isError") or block.get("isError")))


def _pi_message(state: SessionState, message: Any) -> None:
    if not isinstance(message, dict):
        return
    role, blocks = message.get("role"), _blocks(message.get("content"))
    if role == "toolResult":
        _pi_output(state, message, blocks)
        return
    if role == "assistant":
        state.stats["assistant_turns"] += 1
    user_text = False
    for block in blocks:
        user_text = _pi_block(state, role, block) or user_text
    if role == "user" and user_text:
        state.stats["user_turns"] += 1


def _pi_block(state: SessionState, role: Any, block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    if block.get("type") == "toolCall":
        state.tool(str(block.get("name") or "unknown"), _arguments(block.get("arguments") or {}))
    elif block.get("type") == "text":
        text = block.get("text")
        if isinstance(text, str) and role in ("user", "assistant"):
            return state.text(role, text) and role == "user"
    return False


def parse_pi_session(path: Path, _skill_names: Any, _include_subagents: bool) -> Any:
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    state = SessionState()
    meta: dict[str, Any] = {}
    for obj in records:
        ts = obj.get("timestamp")
        state.timestamp(ts)
        if obj.get("type") == "session":
            if not meta:
                meta = {
                    "id": obj.get("id") or path.stem,
                    "cwd": obj.get("cwd"),
                    "started_at": ts,
                    "originator": "pi",
                    "thread_source": None,
                }
            else:
                meta["cwd"] = meta.get("cwd") or obj.get("cwd")
                meta["started_at"] = meta.get("started_at") or ts
        elif obj.get("type") == "message":
            _pi_message(state, obj.get("message"))
    if not meta:
        meta = {
            "id": path.stem,
            "cwd": None,
            "started_at": state.first_ts,
            "originator": "pi",
            "thread_source": None,
        }
    return state.finish(meta, GENERIC_EDIT_TOOLS)


def _openai_message(
    state: SessionState, message: Any, role: Any, *, tool_role: str = "tool"
) -> None:
    text = extract_text(message.get("content"))
    if role == "user":
        if state.text("user", text):
            state.stats["user_turns"] += 1
    elif role == "assistant":
        if text:
            state.stats["assistant_turns"] += 1
            state.append("assistant", text)
        for name, args_text in assistant_tool_calls(message):
            state.tool(name, args_text)
    elif role == tool_role and text:
        state.output(text)


def parse_grok_session(path: Path, _skill_names: Any, _include_subagents: bool) -> Any:
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    state = SessionState()
    for obj in records:
        if obj.get("synthetic_reason"):
            continue
        _openai_message(state, obj, obj.get("type"), tool_role="tool_result")
    meta = {
        "id": path.parent.name,
        "cwd": unquote(path.parent.parent.name),
        "started_at": None,
        "originator": "grok",
        "thread_source": None,
    }
    return state.finish(meta, GENERIC_EDIT_TOOLS)


def _zcode_messages(records: Any) -> Any:
    messages = None
    for obj in records:
        if not isinstance(obj, dict):
            continue
        body = (obj.get("request") or {}).get("body") or {}
        candidate = body.get("messages")
        if isinstance(candidate, list) and candidate:
            messages = candidate
    return messages


def parse_zcode_session(path: Path, skill_names: Any, _include_subagents: bool) -> Any:
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    messages = _zcode_messages(records)
    if not messages:
        return None
    state = SessionState()
    for message in messages:
        if isinstance(message, dict):
            _openai_message(state, message, message.get("role"))
    state.skills.intersection_update(skill_names)
    meta = {
        "id": path.stem.removeprefix("model-io-"),
        "cwd": None,
        "started_at": None,
        "originator": "zcode",
        "thread_source": None,
    }
    result = state.finish(meta, GENERIC_EDIT_TOOLS)
    return result if result[2] else None


def _copilot_events(records: Iterable[Any], include_subagents: bool) -> Iterator[dict[str, Any]]:
    seen, child_calls = set(), set()
    for obj in records:
        if not isinstance(obj, dict) or not isinstance(obj.get("data"), dict):
            continue
        data = obj["data"]
        if obj.get("checkpoint") or obj.get("ephemeral"):
            continue
        child = obj.get("agentId") or data.get("parentToolCallId")
        call_id = data.get("toolCallId")
        if child and isinstance(call_id, str):
            child_calls.add(call_id)
        if not include_subagents and (
            child or (isinstance(call_id, str) and call_id in child_calls)
        ):
            continue
        event_id = obj.get("id")
        if isinstance(event_id, str) and event_id in seen:
            continue
        if isinstance(event_id, str):
            seen.add(event_id)
        yield obj


def _copilot_context(meta: Any, data: Any, ts: Any) -> None:
    context = data.get("context", data)
    if isinstance(context, dict):
        cwd = context.get("cwd") or context.get("gitRoot")
        if isinstance(cwd, str) and cwd:
            meta["cwd"] = meta["cwd"] or cwd
            if cwd not in meta["cwd_history"]:
                meta["cwd_history"].append(cwd)
    meta["started_at"] = meta["started_at"] or data.get("startTime") or ts
    meta["cli_version"] = meta.get("cli_version") or data.get("copilotVersion")


def _copilot_tool_start(state: SessionState, data: Any) -> None:
    name = str(data.get("toolName") or "unknown")
    args = data.get("arguments") or {}
    text = args if isinstance(args, str) else json.dumps(args, sort_keys=True, ensure_ascii=False)
    state.tool(name, text)
    state.edits |= name in GENERIC_EDIT_TOOLS or name in {
        "create",
        "insert_after_symbol",
        "insert_before_symbol",
        "replace_symbol_body",
        "replace_content",
        "replace_in_files",
    }


def _copilot_tool_complete(state: SessionState, data: Any) -> None:
    result, error = data.get("result") or {}, data.get("error") or {}
    text = extract_text(result.get("content")) if isinstance(result, dict) else extract_text(result)
    if isinstance(error, dict) and error.get("message"):
        text += "\n" + str(error["message"])
    state.output(text, data.get("success") is False)


def _copilot_event(state: SessionState, meta: Any, obj: Any) -> None:
    data, kind = obj["data"], obj.get("type")
    if kind in ("session.start", "session.context_changed"):
        _copilot_context(meta, data, obj.get("timestamp"))
    elif kind in ("user.message", "assistant.message"):
        role, text = kind.split(".")[0], extract_text(data.get("content"))
        state.stats[f"{role}_turns"] += 1
        if text:
            state.append(role, text)
    elif kind == "tool.execution_start":
        _copilot_tool_start(state, data)
    elif kind == "tool.execution_complete":
        _copilot_tool_complete(state, data)
    elif kind == "skill.invoked" and isinstance(data.get("name"), str):
        state.skills.add(data["name"])
        state.entries.append(("skill", json.dumps({"skill": data["name"]})))


def parse_copilot_session(
    path: Path,
    skill_names: Collection[str],
    include_subagents: bool,
) -> Any:
    try:
        records = iter_jsonl_records(path)
    except OSError:
        return None
    meta: dict[str, Any] = {
        "id": path.parent.name,
        "cwd": None,
        "started_at": None,
        "originator": "copilot-cli",
        "thread_source": None,
        "cwd_history": [],
    }
    state = SessionState()
    for obj in _copilot_events(records, include_subagents):
        ts = obj.get("timestamp")
        if isinstance(ts, str):
            state.timestamp(ts)
        _copilot_event(state, meta, obj)
    result = state.finish(meta)
    state.skills.update(detect_skills_from_entries(result[2], skill_names))
    return meta, result[1], result[2], sorted(state.skills)
