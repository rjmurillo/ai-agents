"""Compact, redacted session excerpt up to one Stop, for a judge model.

The excerpt shows the first human prompt, later human turns, each tool call
with its outcome, and assistant text. It never shows the four counts, so a
judge cannot anchor on them. ``excerpt_session`` returns the counts apart,
for the CLI to print.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.failure_classifier import canonical_input, classify, events_from_records
from scripts.failure_classifier.transcript import _blocks, _result_text
from scripts.metrics.friction_calibration_samples import clip
from scripts.metrics.friction_calibration_scan import (
    Tracker,
    first_error_line,
    hook,
    iter_records,
    stop_counts,
    user_text,
)

FIRST_PROMPT_CHARS = 300
LATER_TURN_CHARS = 200
TOOL_INPUT_CHARS = 160
ERROR_LINE_CHARS = 200
ASSISTANT_TEXT_CHARS = 200
DEFAULT_MAX_BYTES = 9000


class StopOutOfRangeError(ValueError):
    """The requested Stop index does not exist in the session."""


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


# Only these record types carry the conversation; others, such as
# ``api-request-blob``, embed copies of earlier messages (as in the adapter).
_CONVERSATION_TYPES = frozenset({"assistant", "user"})
# Injected harness text in user or assistant text blocks, not agent prose.
_INJECTED_PREFIXES = ("<system-reminder>", "<local-command", "<command-", "<total_tokens>")
_HOOK_OUTPUT = re.compile(r"^[A-Za-z]+(?::[A-Za-z|*]+)? hook (?:success|additional context|error)")


def _conversation(record: Mapping[str, Any]) -> bool:
    return record.get("isSidechain") is not True and record.get("type") in _CONVERSATION_TYPES


def _injected(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith(_INJECTED_PREFIXES) or bool(_HOOK_OUTPUT.match(stripped))


def _tool_lines(records: list[dict[str, Any]]) -> dict[str, int]:
    """Position of each tool_use id in call order, for ``#n`` numbering."""
    order: dict[str, int] = {}
    for record in records:
        if not _conversation(record) or record.get("type") != "assistant":
            continue
        for block in _blocks(record):
            use_id = block.get("id")
            if block.get("type") == "tool_use" and isinstance(use_id, str):
                order.setdefault(use_id, len(order) + 1)
    return order


def render_lines(records: list[dict[str, Any]]) -> list[str]:
    """One redacted line per human turn, tool call, or assistant text block."""
    order = _tool_lines(records)
    call_index: dict[str, int] = {}
    lines: list[str] = []
    first_prompt_done = False
    for record in records:
        if not _conversation(record):
            continue
        if hook().is_human_turn(record):
            limit = LATER_TURN_CHARS if first_prompt_done else FIRST_PROMPT_CHARS
            label = "HUMAN" if first_prompt_done else "FIRST PROMPT"
            lines.append(f"{label}: {clip(user_text(record), limit)}")
            first_prompt_done = True
            continue
        if not first_prompt_done and record.get("type") == "user":
            # Headless runs have no typed turn; their first real user text is
            # the task prompt the judge needs.
            text = user_text(record)
            if text.strip() and not _injected(text):
                lines.append(f"TASK PROMPT: {clip(text, FIRST_PROMPT_CHARS)}")
                first_prompt_done = True
                continue
        for block in _blocks(record):
            _render_block(block, str(record.get("type")), order, call_index, lines)
    return lines


def _render_block(
    block: Mapping[str, Any],
    record_type: str,
    order: dict[str, int],
    call_index: dict[str, int],
    lines: list[str],
) -> None:
    kind = block.get("type")
    if kind == "text" and isinstance(block.get("text"), str):
        # Assistant prose only; user-record text that is not a human turn is
        # harness injection, and injected text inside either role is skipped.
        if record_type == "assistant" and not _injected(block["text"]):
            lines.append(f"ASSISTANT: {clip(block['text'], ASSISTANT_TEXT_CHARS)}")
    elif (
        kind == "tool_use"
        and record_type == "assistant"
        and isinstance(block.get("id"), str)
        and block["id"] not in call_index
    ):
        number = order.get(block["id"], 0)
        call_index[block["id"]] = len(lines)
        tool_input = clip(canonical_input(block.get("input")), TOOL_INPUT_CHARS)
        lines.append(f"#{number} {block.get('name')} input={tool_input} -> (no result)")
    elif kind == "tool_result" and record_type == "user":
        _render_result(block, call_index, lines)


def _render_result(block: Mapping[str, Any], call_index: dict[str, int], lines: list[str]) -> None:
    position = call_index.get(str(block.get("tool_use_id")))
    if position is None or "-> (no result)" not in lines[position]:
        return
    if block.get("is_error") is True:
        error = clip(first_error_line(_result_text(block.get("content"))), ERROR_LINE_CHARS)
        outcome = f"ERR {error}"
    else:
        outcome = "ok"
    lines[position] = lines[position].replace("-> (no result)", f"-> {outcome}", 1)


def fit_to_budget(lines: list[str], max_bytes: int) -> str:
    """Keep the head line and the newest lines that fit; mark what was cut."""
    text = "\n".join(lines)
    if _byte_len(text) <= max_bytes:
        return text
    head, rest = lines[:1], lines[1:]
    kept: list[str] = []
    marker_room = _byte_len("\n[... 99999 earlier lines elided ...]")
    used = sum(_byte_len(line) + 1 for line in head) + marker_room
    for line in reversed(rest):
        cost = _byte_len(line) + 1
        if used + cost > max_bytes:
            break
        kept.append(line)
        used += cost
    kept.reverse()
    elided = len(rest) - len(kept)
    out = "\n".join([*head, f"[... {elided} earlier lines elided ...]", *kept])
    return out.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def excerpt_session(
    path: Path, stop: int, max_bytes: int = DEFAULT_MAX_BYTES, event: int | None = None
) -> tuple[str, dict[str, int]]:
    """Excerpt of ``path`` up to Stop ``stop``, plus that Stop's four counts.

    With ``event``, the excerpt instead ends at that event's tool_result, so a
    judge sees nothing after a consumer A first fire. The counts stay the
    Stop's.
    """
    tracker = Tracker()
    with path.open(encoding="utf-8", errors="replace") as handle:
        records = list(iter_records(handle, tracker))
    record_bounds = [*tracker.stop_records, len(records)]
    event_bounds = [*tracker.stop_events, tracker.event_count]
    if not 0 <= stop < len(record_bounds):
        raise StopOutOfRangeError(f"stop {stop} not in 0..{len(record_bounds) - 1}")
    prefix = records[: record_bounds[stop]]
    events = events_from_records(prefix)
    counts = stop_counts(classify(events[: event_bounds[stop]]))
    if event is not None:
        if not 0 <= event < len(tracker.event_records):
            raise StopOutOfRangeError(f"event {event} not in 0..{len(tracker.event_records) - 1}")
        prefix = records[: tracker.event_records[event] + 1]
    return fit_to_budget(render_lines(prefix), max_bytes), counts
