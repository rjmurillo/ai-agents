"""Parse one security-guidance child-review transcript into a ``SessionRecord``.

Extraction constants below are verified, this session, against the installed
plugin source (``security-guidance`` 2.0.8, marketplace commit
``55b58ec6e5649104f926ba7558b567dc8d33c5ff``, per
``.project-toolkit/specs/SPEC-5856-security-guidance-diff-prompt-dedup.md``):
``~/.claude/plugins/cache/claude-plugins-official/security-guidance/2.0.8/hooks/llm.py``.
Each constant cites the exact line(s) quoted, and one is verified instead
against a live transcript because the plugin source has no matching string
literal (see ``_STRUCTURED_OUTPUT_TOOL_NAME`` below).

Divergence from the originating task brief (canonical-source-mirror.md):
the brief describing this module's contract stated the iter2 diff body is
terminated by ``"\\n\\n---\\n\\nA prior reviewer"``. Verified against
``llm.py``, that is wrong. ``llm.py:1421-1423`` builds
``iter2_prompt = user_prompt + "\\n\\n---\\n\\nA prior reviewer..."`` on top
of the FULL investigate ``user_prompt``, which already ends with
``"\\n\\nInvestigate per the method in your instructions, then return the
findings list."`` (``llm.py:1220``). So in an iter2 transcript,
``"\\n\\nInvestigate per the method"`` occurs first and
``"\\n\\n---\\n\\nA prior reviewer"`` occurs after it, inside the same
string. Terminating the diff body at the "prior reviewer" marker would
capture the investigate instruction tail and the whole iter2 preamble as
part of the "diff", corrupting ``diff_bytes``/``diff_sha256``/``blocks`` for
every iter2 session. Confirmed against a real transcript line
(``~/.claude/projects/-home-richard-machine-config/
ea28e82d-3530-4969-9d02-aab683771e0b.jsonl`` line 3): the "Investigate per
the method" substring sits at text offset 1056 and "A prior reviewer" at
1137. This module uses ``"\\n\\nInvestigate per the method"`` as the
diff-body terminator for both the investigate and iter2 kinds.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.metrics.sg_prompt_audit_models import (
    Block,
    CapCounts,
    Locator,
    SessionRecord,
    UsageTotals,
)

# --- Prompt classification (llm.py:1214, :1427, :1527) ----------------------

_INVESTIGATE_PREFIX = "Review this change for security vulnerabilities."
"""llm.py:1214: `user_prompt = ("Review this change for security vulnerabilities.\\n\\n" ...`"""

_EXCLUDED_FINDINGS_MARKER = "<excluded_findings>"
"""llm.py:1427: `"<excluded_findings>\\n" + excl + "\\n</excluded_findings>\\n\\n"`"""

_REFUTE_PREFIX = "You previously flagged these candidate vulnerabilities:"
"""llm.py:1527: `"You previously flagged these candidate vulnerabilities:\\n\\n"`"""

# --- Investigate/iter2 body (llm.py:1215-1220) -------------------------------

_DIFF_HEADER = "\n\nUnified diff (only + lines are new):\n\n"
"""llm.py:1218: `+ "\\n\\nUnified diff (only + lines are new):\\n\\n"`"""

_DIFF_BODY_TERMINATOR = "\n\nInvestigate per the method"
"""llm.py:1220: `+ "\\n\\nInvestigate per the method in your instructions, then return "`.

Shared by investigate and iter2; see module docstring divergence note.
"""

_ITER2_SUFFIX_MARKER = "\n\n---\n\nA prior reviewer already flagged"
"""llm.py:1423: `+ "\\n\\n---\\n\\nA prior reviewer already flagged the items inside "`.

Appears only after the real diff-body terminator. A diff under review can
quote ``<excluded_findings>`` or this marker, so iter2 is decided from the
text after the last terminator, never from the whole prompt.
"""

_CHECKOUT_MARKER = "The DIFF below is authoritative"
"""llm.py:1205: `"...The DIFF below is authoritative for what changed..."`. Optional;
present only when `SG_AGENTIC_CONTEXT_DIR` differs from the repo dir."""

# --- Refute body (llm.py:1527-1530) ------------------------------------------

_REFUTE_DIFF_HEADER = "\n\nDIFF:\n"
"""llm.py:1529: `+ "\\n\\nDIFF:\\n" + diff_text[:8000]`"""

_REFUTE_TERMINATOR = "\n\nNow adversarially"
"""llm.py:1530: `+ "\\n\\nNow adversarially try to DISPROVE each one. For each "`"""

# --- Per-file diff blocks (llm.py:1210-1212) ---------------------------------

_BLOCK_MARKER_RE = re.compile(r"=== DIFF: (?P<path>[^\n]*) ===\n")
"""llm.py:1211: `f"=== DIFF: {fp} ===\\n{content}"`, joined by `"\\n\\n"` (llm.py:1210).

A block's ``sha256``/``bytes`` cover ``content`` only (the marker line is
metadata, captured separately as ``path``). For a non-final block, the
literal 2-character `"\\n\\n".join()` separator is stripped from the tail
before hashing, recovering ``content`` exactly as the plugin built it.
"""

# --- Truncation markers (llm.py:240, :244, :248) -----------------------------

_CAP_MARKER_PER_FILE = "[truncated by security-guidance: file exceeds per-file byte cap]"
"""llm.py:240"""

_CAP_MARKER_TOTAL_TRUNCATED = "[truncated by security-guidance: total diff byte cap reached]"
"""llm.py:248"""

_CAP_MARKER_OMITTED = "[omitted by security-guidance: total diff byte cap reached]"
"""llm.py:244"""

# --- Structured-output success marker ----------------------------------------

_STRUCTURED_OUTPUT_TOOL_NAME = "StructuredOutput"
"""Not a string literal in llm.py: the plugin invokes the Agent SDK's
structured-output feature via `schema=...` and reads back `msg.structured_output`
(e.g. llm.py:1353-1354), never naming the tool directly. Verified instead
against a real transcript this session: an assistant entry whose
`message.content` includes `{"type": "tool_use", "name": "StructuredOutput"}`,
the SDK's synthetic tool call for structured output.
"""

_USAGE_FIELDS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


def classify_prompt(text: str) -> str | None:
    """Return "investigate", "iter2", "refute", or None for a non-review prompt."""
    if text.startswith(_INVESTIGATE_PREFIX):
        end_idx = text.rfind(_DIFF_BODY_TERMINATOR)
        tail = text[end_idx:] if end_idx != -1 else ""
        is_iter2 = _ITER2_SUFFIX_MARKER in tail and _EXCLUDED_FINDINGS_MARKER in tail
        return "iter2" if is_iter2 else "investigate"
    if text.startswith(_REFUTE_PREFIX):
        return "refute"
    return None


def _extract_investigate_diff(text: str) -> tuple[str, bool]:
    header_idx = text.find(_DIFF_HEADER)
    if header_idx == -1:
        return "", _CHECKOUT_MARKER in text
    checkout_note = _CHECKOUT_MARKER in text[:header_idx]
    start = header_idx + len(_DIFF_HEADER)
    # rfind, not find: the reviewed diff can quote the terminator as data. The
    # plugin appends the real terminator after the diff, and nothing after it
    # carries a blank line plus this text (iter2 exclusions are whitespace-collapsed).
    end_idx = text.rfind(_DIFF_BODY_TERMINATOR, start)
    diff_body = text[start:end_idx] if end_idx != -1 else text[start:]
    return diff_body, checkout_note


def _extract_refute_diff(text: str) -> str:
    header_idx = text.find(_REFUTE_DIFF_HEADER)
    if header_idx == -1:
        return ""
    start = header_idx + len(_REFUTE_DIFF_HEADER)
    # rfind for the same reason: the capped diff can quote the refute tail.
    end_idx = text.rfind(_REFUTE_TERMINATOR, start)
    return text[start:end_idx] if end_idx != -1 else text[start:]


def extract_diff_and_checkout(text: str, kind: str) -> tuple[str, bool]:
    """Return ``(diff_body, checkout_note)`` for the given prompt ``kind``."""
    if kind == "refute":
        return _extract_refute_diff(text), False
    return _extract_investigate_diff(text)


def extract_blocks(diff_body: str) -> list[Block]:
    """Split ``diff_body`` into its ``=== DIFF: <path> ===`` sections, in order."""
    matches = list(_BLOCK_MARKER_RE.finditer(diff_body))
    blocks: list[Block] = []
    last_index = len(matches) - 1
    for index, match in enumerate(matches):
        content_start = match.end()
        content_end = len(diff_body) if index == last_index else matches[index + 1].start()
        content = diff_body[content_start:content_end]
        if index != last_index:
            content = content[:-2]  # strip the "\n\n".join() separator
        payload = content.encode("utf-8")
        blocks.append(
            Block(
                path=match.group("path"),
                sha256=hashlib.sha256(payload).hexdigest(),
                bytes=len(payload),
            )
        )
    return blocks


def count_caps(diff_body: str) -> CapCounts:
    """Count occurrences of the three security-guidance truncation markers."""
    return CapCounts(
        per_file_truncated=diff_body.count(_CAP_MARKER_PER_FILE),
        total_truncated=diff_body.count(_CAP_MARKER_TOTAL_TRUNCATED),
        omitted=diff_body.count(_CAP_MARKER_OMITTED),
    )


def extract_message_text(content: object) -> str:
    """Return the plain text of a transcript entry's ``message.content``.

    Handles both shapes the spec documents: a plain string, or a list of
    ``{"type": "text", "text": ...}`` items (other item types, such as
    ``tool_use`` or ``thinking``, contribute no text).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def has_structured_output(entry: dict[str, Any]) -> bool:
    """True when an assistant entry's content carries the StructuredOutput tool call."""
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return False
    for item in content:
        if (
            isinstance(item, dict)
            and item.get("type") == "tool_use"
            and item.get("name") == _STRUCTURED_OUTPUT_TOOL_NAME
        ):
            return True
    return False


def usage_from_entry(entry: dict[str, Any]) -> UsageTotals:
    """Read the four usage fields off an assistant entry's ``message.usage``."""
    message = entry.get("message")
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        usage = {}
    values = {}
    for name in _USAGE_FIELDS:
        raw = usage.get(name)
        values[name] = int(raw) if isinstance(raw, int) else 0
    return UsageTotals(**values)


def add_usage(a: UsageTotals, b: UsageTotals) -> UsageTotals:
    """Sum two usage totals field by field."""
    return UsageTotals(
        input_tokens=a.input_tokens + b.input_tokens,
        cache_creation_input_tokens=a.cache_creation_input_tokens + b.cache_creation_input_tokens,
        cache_read_input_tokens=a.cache_read_input_tokens + b.cache_read_input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
    )


def parse_timestamp(value: str) -> datetime:
    """Parse a security-guidance transcript's ISO-Z timestamp."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latency_seconds(start: str, end: str) -> float:
    """Seconds between two ISO-Z timestamps; 0.0 when either is missing or unparsable."""
    if not start or not end:
        return 0.0
    try:
        return (parse_timestamp(end) - parse_timestamp(start)).total_seconds()
    except ValueError:
        return 0.0


@dataclass
class _ParseState:
    """Mutable accumulator for one transcript file's single streaming pass."""

    first_user_text: str | None = None
    first_user_line: int | None = None
    first_user_ts: str | None = None
    cwd: str | None = None
    kind: str | None = None
    last_ts: str | None = None
    assistant_turns: int = 0
    usage_total: UsageTotals = field(default_factory=lambda: UsageTotals(0, 0, 0, 0))
    first_turn_usage: UsageTotals | None = None
    succeeded: bool = False
    skipped_lines: int = 0
    stop: bool = False


@dataclass(frozen=True, slots=True)
class _RecordContext:
    """The three fields ``_ParseState`` narrows from Optional before finalizing."""

    project: str
    file_name: str
    line: int
    kind: str
    first_user_text: str


def _update_timestamp(state: _ParseState, entry: dict[str, Any]) -> None:
    ts = entry.get("timestamp")
    if isinstance(ts, str) and ts:
        state.last_ts = ts


def _handle_first_user_entry(state: _ParseState, entry: dict[str, Any], line_no: int) -> None:
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    text = extract_message_text(content)
    kind = classify_prompt(text)
    if kind is None:
        state.stop = True
        return
    state.first_user_text = text
    state.first_user_line = line_no
    ts = entry.get("timestamp")
    state.first_user_ts = ts if isinstance(ts, str) else None
    cwd_value = entry.get("cwd")
    state.cwd = cwd_value if isinstance(cwd_value, str) else None
    state.kind = kind


def _handle_assistant_entry(state: _ParseState, entry: dict[str, Any]) -> None:
    state.assistant_turns += 1
    usage = usage_from_entry(entry)
    if state.assistant_turns == 1:
        state.first_turn_usage = usage
    state.usage_total = add_usage(state.usage_total, usage)
    if has_structured_output(entry):
        state.succeeded = True


def _handle_entry(state: _ParseState, entry: dict[str, Any], line_no: int) -> None:
    _update_timestamp(state, entry)
    entry_type = entry.get("type")
    if state.first_user_text is None:
        if entry_type == "user":
            _handle_first_user_entry(state, entry, line_no)
        return
    if entry_type == "assistant":
        _handle_assistant_entry(state, entry)


def _finalize_record(ctx: _RecordContext, state: _ParseState) -> SessionRecord:
    diff_body, checkout_note = extract_diff_and_checkout(ctx.first_user_text, ctx.kind)
    blocks = extract_blocks(diff_body)
    cap = count_caps(diff_body)
    prompt_payload = ctx.first_user_text.encode("utf-8")
    diff_payload = diff_body.encode("utf-8")
    path_order = "\n".join(block.path for block in blocks)
    started_at = state.first_user_ts or ""
    ended_at = state.last_ts or started_at
    failure = None
    if not state.succeeded:
        failure = "no_assistant" if state.assistant_turns == 0 else "no_structured_output"
    return SessionRecord(
        locator=Locator(project=ctx.project, file=ctx.file_name, line=ctx.line),
        kind=ctx.kind,
        cwd=state.cwd or "",
        started_at=started_at,
        ended_at=ended_at,
        latency_s=latency_seconds(started_at, ended_at),
        prompt_bytes=len(prompt_payload),
        prompt_sha256=hashlib.sha256(prompt_payload).hexdigest(),
        diff_bytes=len(diff_payload),
        diff_sha256=hashlib.sha256(diff_payload).hexdigest(),
        blocks=tuple(blocks),
        path_order_sha256=hashlib.sha256(path_order.encode("utf-8")).hexdigest(),
        cap=cap,
        checkout_note=checkout_note,
        assistant_turns=state.assistant_turns,
        usage=state.usage_total,
        first_turn_usage=state.first_turn_usage,
        succeeded=state.succeeded,
        failure=failure,
    )


def process_transcript_file(path: Path, project: str) -> tuple[SessionRecord | None, int]:
    """Parse one JSONL transcript file.

    Returns ``(record, skipped_lines)``. ``record`` is ``None`` when the file
    carries no user entry, or when its first user entry's text does not
    classify as a review prompt (REQ-3): the rest of the file is not read in
    that case. ``skipped_lines`` counts malformed JSON lines and non-object
    JSON values, wherever in the file they occur before the parse stops.
    """
    state = _ParseState()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                state.skipped_lines += 1
                continue
            if not isinstance(entry, dict):
                state.skipped_lines += 1
                continue
            _handle_entry(state, entry, line_no)
            if state.stop:
                break
    first_user_text = state.first_user_text
    kind = state.kind
    first_user_line = state.first_user_line
    if first_user_text is None or kind is None or first_user_line is None:
        return None, state.skipped_lines
    ctx = _RecordContext(
        project=project,
        file_name=path.name,
        line=first_user_line,
        kind=kind,
        first_user_text=first_user_text,
    )
    return _finalize_record(ctx, state), state.skipped_lines
