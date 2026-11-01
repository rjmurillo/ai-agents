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
- an ``isSidechain`` flag on every record.

Each non-sidechain ``tool_use`` and its ``tool_result`` become exactly one
FailureEvent, in result order. A use with no result yet emits nothing. A use
with no ``input`` (or a null one) gets no ProgressKey, as in consumer A.

No shipped caller uses this module yet: the planned Stop retrospective nudge
(consumer B) will. Tests pin it to consumer A through the AC-36 parity test.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .classifier import (
    EDIT_TOOLS,
    FailureEvent,
    canonical_input,
    normalize_tool,
)

# REQ-048 Definitions: `target` is the `file_path`, `notebook_path`, or `path`
# input field, first present, when the tool is an edit tool.
_TARGET_FIELDS: tuple[str, ...] = ("file_path", "notebook_path", "path")


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
    """
    uses: dict[str, tuple[str, object]] = {}
    events: list[FailureEvent] = []
    for record in records:
        if not isinstance(record, Mapping) or record.get("isSidechain") is True:
            continue
        for block in _blocks(record):
            kind = block.get("type")
            if kind == "tool_use":
                use_id, name = block.get("id"), block.get("name")
                if isinstance(use_id, str) and isinstance(name, str) and name.strip():
                    uses[use_id] = (name, block.get("input"))
            elif kind == "tool_result":
                use_id = block.get("tool_use_id")
                use = uses.pop(use_id, None) if isinstance(use_id, str) else None
                if use is None:
                    continue
                name, tool_input = use
                events.append(
                    FailureEvent.build(
                        tool=name,
                        ok=block.get("is_error") is not True,
                        error=_result_text(block.get("content")),
                        input=None if tool_input is None else canonical_input(tool_input),
                        target=_target(name, tool_input),
                    )
                )
    return events
