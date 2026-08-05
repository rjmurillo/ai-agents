"""Read model-attributed answers from Copilot CLI session transcripts."""

from __future__ import annotations

import json
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from _copilot_windows_files import open_windows_transcript
from _eval_common import MalformedProviderMetadataError, require_str_or_none

_COPILOT_HOME_ENV = "COPILOT_HOME"
_MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
_MAX_SESSION_ENTRIES = 4096
_MAX_TRANSCRIPT_CANDIDATES = 256
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


@dataclass(frozen=True, slots=True)
class _TranscriptCandidate:
    session_name: str
    modified_at: float


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
    if model and _MODEL_ID_RE.fullmatch(model) is None:
        raise MalformedProviderMetadataError(
            "provider metadata field 'model' has invalid format"
        )
    return content.strip(), model


def _model_that_spoke(
    message_models: list[str],
    *,
    unattributed: bool,
) -> str | None:
    if unattributed or len(message_models) != 1:
        return None
    return message_models[0]


def _open_transcript(
    root: Path,
    session_name: str,
    provider_label: str,
) -> tuple[int, os.stat_result]:
    file_flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    file_flags |= getattr(os, "O_NOFOLLOW", 0)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)

    if os.name == "nt":
        return cast(
            tuple[int, os.stat_result],
            open_windows_transcript(root, session_name, provider_label),
        )
    else:
        root_descriptor = os.open(root, directory_flags)
        try:
            session_descriptor = os.open(
                session_name,
                directory_flags,
                dir_fd=root_descriptor,
            )
            try:
                descriptor = os.open(
                    "events.jsonl",
                    file_flags,
                    dir_fd=session_descriptor,
                )
            finally:
                os.close(session_descriptor)
        finally:
            os.close(root_descriptor)

    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise RuntimeError(
            f"{provider_label} session transcript is not a regular file"
        )
    return descriptor, metadata


def _read_matching_session(
    root: Path,
    candidate: _TranscriptCandidate,
    sandbox: str,
    provider_label: str,
    since: float,
    deadline: float,
) -> tuple[str, str | None] | None:
    matched = False
    message_models: list[str] = []
    unattributed = False
    chunks: list[str] = []
    total_chars = 0
    try:
        descriptor, metadata = _open_transcript(
            root,
            candidate.session_name,
            provider_label,
        )
        if metadata.st_mtime < since:
            os.close(descriptor)
            return None
        with os.fdopen(
            descriptor,
            encoding="utf-8",
            errors="replace",
        ) as stream:
            while True:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"{provider_label} session transcript scan timed out"
                    )
                raw_line = stream.readline(_MAX_TRANSCRIPT_LINE_CHARS + 1)
                if not raw_line:
                    break
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
    deadline: float,
) -> tuple[str, str | None] | None:
    """Return the answer and the one model that authored all accepted text."""
    candidates: list[_TranscriptCandidate] = []
    entries_seen = 0
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                entries_seen += 1
                if entries_seen > _MAX_SESSION_ENTRIES:
                    raise RuntimeError(
                        f"{provider_label} session directory entry limit exceeded"
                    )
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"{provider_label} session transcript scan timed out"
                    )
                if not entry.is_dir(follow_symlinks=False):
                    continue
                path = Path(entry.path) / "events.jsonl"
                try:
                    metadata = path.lstat()
                except OSError:
                    continue
                if (
                    stat.S_ISLNK(metadata.st_mode)
                    or not stat.S_ISREG(metadata.st_mode)
                ):
                    raise RuntimeError(
                        f"{provider_label} session transcript is not a regular file"
                    )
                if metadata.st_mtime < since:
                    continue
                candidates.append(
                    _TranscriptCandidate(entry.name, metadata.st_mtime)
                )
                if len(candidates) > _MAX_TRANSCRIPT_CANDIDATES:
                    raise RuntimeError(
                        f"{provider_label} session transcript candidate limit exceeded"
                    )
    except OSError:
        return None
    candidates.sort(key=lambda candidate: candidate.session_name)
    for candidate in candidates:
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"{provider_label} session transcript scan timed out"
            )
        transcript = _read_matching_session(
            root,
            candidate,
            sandbox,
            provider_label,
            since,
            deadline,
        )
        if transcript is not None:
            return transcript
    return None
