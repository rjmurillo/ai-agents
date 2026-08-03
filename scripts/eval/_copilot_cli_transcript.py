"""Read model-attributed answers from Copilot CLI session transcripts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from _eval_common import require_str_or_none


def _session_state_root(env_name: str, provider_label: str) -> Path:
    override = os.environ.get(env_name)
    if not override:
        return Path.home() / ".copilot" / "session-state"
    root = Path(override)
    if root.is_absolute():
        return root
    raise RuntimeError(
        f"{provider_label} needs {env_name} to be absolute; got {override!r}, "
        "which the CLI resolves against a per-call sandbox this process cannot read."
    )


def _read_candidate(path: Path, since: float) -> str | None:
    try:
        if path.stat().st_mtime < since:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _parse_event(
    line: str,
) -> tuple[str, dict[str, object], dict[str, object]] | None:
    try:
        raw_event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw_event, dict):
        return None
    event = cast(dict[str, object], raw_event)
    raw_data = event.get("data")
    if not isinstance(raw_data, dict):
        return None
    kind = event.get("type")
    if not isinstance(kind, str):
        return None
    return kind, cast(dict[str, object], raw_data), event


def _is_subagent_message(
    event: dict[str, object],
    data: dict[str, object],
) -> bool:
    return "agentId" in event or "parentToolCallId" in data


def _read_assistant_message(
    event: dict[str, object],
    data: dict[str, object],
    provider_label: str,
) -> tuple[str, str | None] | None:
    if _is_subagent_message(event, data):
        return None
    content = data.get("content")
    if not isinstance(content, str):
        raise RuntimeError(
            f"{provider_label} session transcript is malformed: an assistant "
            f"message carries content of type {type(content).__name__}, not text. "
            "Reading past it would grade a truncated answer as whole, so the run "
            "is refused."
        )
    if not content.strip():
        return None
    model = require_str_or_none(data.get("model"), "model")
    return content.strip(), model


def _model_that_spoke(
    message_models: list[str],
    *,
    unattributed: bool,
) -> str | None:
    if unattributed or len(message_models) != 1:
        return None
    return message_models[0]


def _read_matching_session(
    raw: str,
    sandbox: str,
    provider_label: str,
) -> tuple[str, str | None] | None:
    matched = False
    message_models: list[str] = []
    unattributed = False
    chunks: list[str] = []
    for raw_line in raw.splitlines():
        parsed = _parse_event(raw_line.strip())
        if parsed is None:
            continue
        kind, data, event = parsed
        if kind == "session.start":
            context = data.get("context")
            cwd = context.get("cwd") if isinstance(context, dict) else None
            if cwd != sandbox:
                return None
            matched = True
            continue
        if kind != "assistant.message" or not matched:
            continue
        accepted = _read_assistant_message(event, data, provider_label)
        if accepted is None:
            continue
        content, model = accepted
        chunks.append(content)
        if model and model not in message_models:
            message_models.append(model)
        if not model:
            unattributed = True
    if not matched:
        return None
    return "\n\n".join(chunks), _model_that_spoke(
        message_models,
        unattributed=unattributed,
    )


def read_session_transcript(
    sandbox: str,
    *,
    since: float,
    env_name: str,
    provider_label: str,
) -> tuple[str, str | None] | None:
    """Return the answer and the one model that authored all accepted text."""
    root = _session_state_root(env_name, provider_label)
    try:
        candidates = sorted(root.glob("*/events.jsonl"))
    except OSError:
        return None
    for path in candidates:
        raw = _read_candidate(path, since)
        if raw is None:
            continue
        transcript = _read_matching_session(raw, sandbox, provider_label)
        if transcript is not None:
            return transcript
    return None
