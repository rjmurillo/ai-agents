"""Read model-attributed answers from Copilot CLI session transcripts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from _eval_common import require_str_or_none

_COPILOT_HOME_ENV = "COPILOT_HOME"
_MAX_TRANSCRIPT_LINE_CHARS = 1024 * 1024
_MAX_TRANSCRIPT_CHARS = 4 * 1024 * 1024


def session_state_root(env_name: str, provider_label: str) -> Path:
    """Resolve and validate the one session root shared with the child."""
    override = os.environ.get(env_name)
    if override:
        root = Path(override)
        if root.is_absolute():
            return root
        raise RuntimeError(
            f"{provider_label} needs {env_name} to be absolute; got {override!r}"
        )
    copilot_home = os.environ.get(_COPILOT_HOME_ENV)
    if copilot_home:
        home = Path(copilot_home)
        if home.is_absolute():
            return home / "session-state"
        raise RuntimeError(
            f"{provider_label} needs {_COPILOT_HOME_ENV} to be absolute; "
            f"got {copilot_home!r}"
        )
    home = Path.home()
    if not home.is_absolute():
        raise RuntimeError(
            f"{provider_label} needs the home directory to be absolute"
        )
    return home / ".copilot" / "session-state"


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
    path: Path,
    sandbox: str,
    provider_label: str,
    since: float,
) -> tuple[str, str | None] | None:
    matched = False
    message_models: list[str] = []
    unattributed = False
    chunks: list[str] = []
    total_chars = 0
    try:
        if path.stat().st_mtime < since:
            return None
        with path.open(encoding="utf-8", errors="replace") as stream:
            for raw_line in stream:
                total_chars += len(raw_line)
                if (
                    len(raw_line) > _MAX_TRANSCRIPT_LINE_CHARS
                    or total_chars > _MAX_TRANSCRIPT_CHARS
                ):
                    raise RuntimeError(
                        f"{provider_label} session transcript exceeded the size limit"
                    )
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
    except OSError:
        return None
    if not matched:
        return None
    return "\n\n".join(chunks), _model_that_spoke(
        message_models,
        unattributed=unattributed,
    )


def read_session_transcript(
    root: Path,
    sandbox: str,
    *,
    since: float,
    provider_label: str,
) -> tuple[str, str | None] | None:
    """Return the answer and the one model that authored all accepted text."""
    try:
        candidates = sorted(root.glob("*/events.jsonl"))
    except OSError:
        return None
    for path in candidates:
        transcript = _read_matching_session(
            path,
            sandbox,
            provider_label,
            since,
        )
        if transcript is not None:
            return transcript
    return None
