"""Transcript adapter: Claude Code transcript records into FailureEvents (AC-38).

Consumer B reads the transcript itself, with its own byte, line, and time
budgets, and passes the decoded records here. This module only maps records
to events; it opens nothing.

Record shapes, observed in Claude Code transcripts (2026-11-01):

- an ``assistant`` record whose ``message.content`` holds
  ``{"type": "tool_use", "id", "name", "input"}`` blocks;
- a ``user`` record whose ``message.content`` holds
  ``{"type": "tool_result", "tool_use_id", "content", "is_error"?}`` blocks,
  where ``content`` is a string or a list of blocks and ``is_error`` is
  present only when true;
- an ``isSidechain`` flag on every record;
- other record types, such as ``api-request-blob``, that embed copies of
  earlier messages and are ignored.

Each non-sidechain ``tool_use`` and its ``tool_result`` become exactly one
FailureEvent, in result order. A use with no result yet emits nothing. A use
with no ``input`` key gets no ProgressKey; an explicit null keys as ``null``.

No shipped caller uses this module yet: the planned Stop retrospective nudge
(consumer B) will. Tests pin it to consumer A through the AC-36 parity test.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from scripts.failure_classifier.classifier import (
    EDIT_TOOLS,
    FailureEvent,
    canonical_input,
    normalize_tool,
)

# REQ-048 Definitions: `target` is the `file_path`, `notebook_path`, or `path`
# input field, first present, when the tool is an edit tool.
_TARGET_FIELDS: tuple[str, ...] = ("file_path", "notebook_path", "path")

# Marks a tool_use with no ``input`` key, which gets no ProgressKey. An
# explicit JSON null is input and serializes as ``null`` (AC-38), as consumer A
# keys the string ``"null"`` (AC-39).
_NO_INPUT = object()

# The text a blocking Stop hook adds as a user record to continue the turn.
STOP_FEEDBACK_PREFIX = "Stop hook feedback:"

# The record types that carry the conversation's own tool calls.
_CONVERSATION_TYPES: frozenset[str] = frozenset({"assistant", "user"})


def _result_text(content: object) -> str:
    """The text of a tool_result: the string itself, or its text blocks joined."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block["text"]
            for block in content
            if isinstance(block, Mapping)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        return "\n".join(parts)
    return ""


def _blocks(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    message = record.get("message")
    if not isinstance(message, Mapping):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, Mapping)]


def _target(name: str, tool_input: object) -> str | None:
    if normalize_tool(name) not in EDIT_TOOLS or not isinstance(tool_input, Mapping):
        return None
    for field_name in _TARGET_FIELDS:
        value = tool_input.get(field_name)
        if isinstance(value, str) and value.strip():
            return value
    return None


def events_from_records(records: Iterable[object]) -> list[FailureEvent]:
    """Pair each non-sidechain tool_use with its tool_result (AC-38).

    Records that are not objects, or lack the expected shape, are skipped.
    A resumed or compacted session can repeat earlier records, so a
    ``tool_use`` id already paired emits nothing a second time.
    """
    uses: dict[str, tuple[str, object]] = {}
    paired: set[str] = set()
    events: list[FailureEvent] = []
    for record in records:
        if not isinstance(record, Mapping) or record.get("isSidechain") is True:
            continue
        # Only conversation records count. Other record types, such as
        # ``api-request-blob``, embed copies of earlier messages.
        record_type = record.get("type")
        if record_type not in _CONVERSATION_TYPES:
            continue
        for block in _blocks(record):
            kind = block.get("type")
            if kind == "tool_use" and record_type == "assistant":
                use_id, name = block.get("id"), block.get("name")
                if (
                    isinstance(use_id, str)
                    and use_id not in paired
                    and isinstance(name, str)
                    and name.strip()
                ):
                    uses[use_id] = (name, block["input"] if "input" in block else _NO_INPUT)
            elif kind == "tool_result" and record_type == "user":
                result_id = block.get("tool_use_id")
                if not isinstance(result_id, str):
                    continue
                use = uses.pop(result_id, None)
                if use is None:
                    continue
                paired.add(result_id)
                name, tool_input = use
                events.append(
                    FailureEvent.build(
                        tool=name,
                        ok=block.get("is_error") is not True,
                        error=_result_text(block.get("content")),
                        input=None if tool_input is _NO_INPUT else canonical_input(tool_input),
                        target=_target(name, tool_input),
                    )
                )
    return events


def _user_text(record: Mapping[str, Any]) -> str:
    """A user record's text: the string itself, or its text blocks joined by a space."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if isinstance(content, str):
        return content
    return " ".join(
        block["text"]
        for block in _blocks(record)
        if block.get("type") == "text" and isinstance(block.get("text"), str)
    )


def is_stop_feedback(record: Mapping[str, Any]) -> bool:
    """True for a user record whose text, once left-trimmed, opens with the Stop hook text.

    Records carrying a ``toolUseResult`` are tool results, never feedback.
    Sidechain handling belongs to the caller; ``stop_feedback_count`` skips them.
    """
    if record.get("type") != "user" or "toolUseResult" in record:
        return False
    return _user_text(record).lstrip().startswith(STOP_FEEDBACK_PREFIX)


def stop_feedback_count(records: Iterable[object]) -> int:
    """Count non-sidechain user records opening with ``Stop hook feedback:``.

    That is the continuation Claude Code adds after a blocking Stop hook.
    Records that are not objects are skipped.
    """
    return sum(
        1
        for record in records
        if isinstance(record, Mapping)
        and record.get("isSidechain") is not True
        and is_stop_feedback(record)
    )
