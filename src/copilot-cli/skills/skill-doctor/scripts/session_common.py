"""Transcript primitives for the MIT-licensed skill-doctor collector.

Copyright (c) 2026 Denver Technologies, Inc. See ../LICENSE.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

MAX_MSG_CHARS = 1500
MAX_TOOL_CHARS = 500
MAX_TRANSCRIPT_ENTRIES = 160
TRANSCRIPT_HEAD = 100
TRANSCRIPT_TAIL = 40
CODE_EDIT_HINTS = (
    "apply_patch",
    "*** Begin Patch",
    "edit_file",
    "create_file",
    "str_replace",
    "write_file",
)
CLAUDE_CODE_EDIT_TOOLS = {"Edit", "MultiEdit", "NotebookEdit", "Write"}
GENERIC_EDIT_TOOLS = {
    "edit",
    "write",
    "apply_patch",
    "edit_file",
    "write_file",
    "str_replace",
    "search_replace",
}
_COLLECTION_ISSUES: ContextVar[Counter[str] | None] = ContextVar("collection_issues", default=None)


@contextmanager
def collect_diagnostics() -> Iterator[None]:
    token = _COLLECTION_ISSUES.set(Counter())
    try:
        yield
    finally:
        _COLLECTION_ISSUES.reset(token)


def record_collection_issue(kind: str, count: int = 1) -> None:
    issues = _COLLECTION_ISSUES.get()
    if issues is not None:
        issues[kind] += count
    else:
        print(f"warning: collection {kind}: {count}", file=sys.stderr)


def collection_issue_counts() -> dict[str, int]:
    return dict(_COLLECTION_ISSUES.get() or {})


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f" …[truncated {len(text) - limit} chars]"


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict):
            text = block.get("text") or block.get("content") or ""
        else:
            text = block
        if isinstance(text, str) and (text or isinstance(block, str)):
            parts.append(text)
    return "\n".join(parts)


def iter_jsonl_records(path: Path) -> Iterator[dict[str, Any]]:
    """Open eagerly so callers can catch missing files before iteration."""
    try:
        stream = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        record_collection_issue("read_failures")
        raise

    def records() -> Iterator[dict[str, Any]]:
        malformed = 0
        with stream:
            try:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        malformed += 1
                        continue
                    if isinstance(record, dict):
                        yield record
                    else:
                        malformed += 1
            except OSError:
                record_collection_issue("read_failures")
            finally:
                if malformed:
                    record_collection_issue("malformed_records", malformed)

    return records()


class TranscriptBuffer:
    """Keep complete short transcripts and a bounded head/tail for long ones."""

    def __init__(self) -> None:
        self._entries: list[tuple[str, str]] = []
        self._tail: deque[tuple[str, str]] | None = None
        self._total = 0

    def append(self, entry: tuple[str, str]) -> None:
        self._total += 1
        if self._tail is not None:
            self._tail.append(entry)
            return
        self._entries.append(entry)
        if len(self._entries) > MAX_TRANSCRIPT_ENTRIES:
            self._tail = deque(self._entries[-TRANSCRIPT_TAIL:], maxlen=TRANSCRIPT_TAIL)
            self._entries = self._entries[:TRANSCRIPT_HEAD]

    def finish(self) -> list[tuple[str, str]]:
        if self._tail is None:
            return self._entries
        omitted = self._total - TRANSCRIPT_HEAD - TRANSCRIPT_TAIL
        return self._entries + [("note", f"[... {omitted} entries omitted ...]")] + list(self._tail)


def detect_skill_candidates(text: str) -> set[str]:
    normalized = text.replace("\\", "/")
    candidates = set(re.findall(r"(?:^|/)skills/+([^/]+)/+", normalized))
    candidates.update(re.findall(r'"(?:skill|name|bundled_skill_id)"\s*:\s*"([^"]+)"', normalized))
    return candidates


def detect_skills_from_entries(entries: Any, skill_names: Any) -> set[str]:
    tool_text = "\n".join(
        text for role, text in entries if role == "skill" or role.startswith("tool:")
    ).replace("\\", "/")
    detected = set()
    for name in skill_names:
        markers = (
            f"skills/{name}/",
            f"{name}/SKILL.md",
            f'"skill": "{name}"',
            f'"name": "{name}"',
            f'"bundled_skill_id": "{name}"',
        )
        if any(marker in tool_text for marker in markers):
            detected.add(name)
    return detected


def looks_injected(text: str) -> bool:
    head = text.lstrip()[:80]
    return head.startswith("<") and any(
        tag in head
        for tag in (
            "environment_context",
            "user_instructions",
            "ENVIRONMENT",
            "system-reminder",
            "permissions",
            "collaboration_mode",
            "recommended_plugins",
            "turn_context",
            "user_info",
        )
    )


def assistant_tool_calls(message: Any) -> list[tuple[str, str]]:
    calls = []
    for call in message.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        fn = call.get("function") or {}
        name = call.get("name") or fn.get("name") or "unknown"
        args = call.get("arguments")
        if args is None:
            args = fn.get("arguments")
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        calls.append((str(name), args))
    return calls


class SessionState:
    """Accumulate parser-local statistics without sharing mutable state."""

    def __init__(self, *, bounded: bool = True) -> None:
        self.stats: dict[str, Any] = dict.fromkeys(
            ("user_turns", "assistant_turns", "tool_calls", "repeated_tool_calls", "error_outputs"),
            0,
        )
        self.entries: Any = TranscriptBuffer() if bounded else []
        self.skills: set[str] = set()
        self.tools: set[str] = set()
        self.calls: set[str] = set()
        self.edits = False
        self.first_ts: Any = None
        self.last_ts: Any = None

    def timestamp(self, ts: Any) -> None:
        if ts:
            self.first_ts = self.first_ts or ts
            self.last_ts = ts

    def append(self, role: str, text: str, limit: int = MAX_MSG_CHARS) -> None:
        self.entries.append((role, truncate(text, limit)))

    def tool(
        self, name: str, text: str, *, hints: bool = True, skill_candidates: bool = True
    ) -> None:
        self.stats["tool_calls"] += 1
        key = hashlib.sha256((name + text).encode()).hexdigest()
        self.stats["repeated_tool_calls"] += int(key in self.calls)
        self.calls.add(key)
        self.tools.add(name)
        if skill_candidates:
            self.skills.update(detect_skill_candidates(text))
        if hints:
            self.edits = self.edits or any(hint in text for hint in CODE_EDIT_HINTS)
        self.append(f"tool:{name}", text, MAX_TOOL_CHARS)

    def output(self, text: str, error: bool = False, *, role: str = "output") -> None:
        low = text[:2000].lower()
        self.stats["error_outputs"] += int(
            error or any(marker in low for marker in ("error", "failed", "traceback"))
        )
        self.append(role, text, MAX_TOOL_CHARS)

    def text(self, role: str, text: str) -> bool:
        if not text or looks_injected(text):
            return False
        self.append(role, text)
        return True

    def finish(self, meta: Any, edit_tools: Any = ()) -> Any:
        self.stats.update(
            first_ts=self.first_ts,
            last_ts=self.last_ts,
            has_code_edits=self.edits or bool(self.tools & set(edit_tools)),
        )
        entries = (
            self.entries.finish() if isinstance(self.entries, TranscriptBuffer) else self.entries
        )
        return meta, self.stats, entries, sorted(self.skills)


def render_transcript(meta: Any, stats: Any, skills_used: Any, entries: Any) -> str:
    lines = [
        f"# Session {meta.get('id')}",
        f"- cwd: {meta.get('cwd')}",
        f"- started: {meta.get('started_at') or stats.get('first_ts')}",
        f"- skills detected: {', '.join(skills_used) or '(none)'}",
        f"- stats: {stats['user_turns']} user turns, {stats['assistant_turns']} assistant turns, "
        f"{stats['tool_calls']} tool calls ({stats['repeated_tool_calls']} repeated), "
        f"{stats['error_outputs']} error-ish outputs, code edits: {stats['has_code_edits']}",
        "",
        "## Condensed transcript",
        "",
    ]
    shown = entries
    if len(entries) > MAX_TRANSCRIPT_ENTRIES:
        omitted = len(entries) - TRANSCRIPT_HEAD - TRANSCRIPT_TAIL
        shown = (
            entries[:TRANSCRIPT_HEAD]
            + [("note", f"[... {omitted} entries omitted ...]")]
            + entries[-TRANSCRIPT_TAIL:]
        )
    for role, text in shown:
        lines.extend((f"[{role}] {text}", ""))
    return "\n".join(lines)
