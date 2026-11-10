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
from datetime import datetime, timedelta, timezone
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


_QUALIFIED_SKILL = re.compile(r"^[\w.-]+:([\w.-]+)$")
_SKILL_KEY = r'"(?:skill|name|bundled_skill_id)"\s*:\s*"'
# Only these keys name an invocation. Generic "name" values such as "area:review" are labels.
_INVOKE_KEY = r'"(?:skill|bundled_skill_id)"\s*:\s*"'


def logical_skill_name(candidate: Any) -> Any:
    """Return the bare name of a `namespace:name` invocation, else the input.

    The namespace is not checked against any definition. Callers record that
    through `skill_evidence`, never as proof of which definition ran.
    """
    match = _QUALIFIED_SKILL.match(candidate) if isinstance(candidate, str) else None
    return match.group(1) if match else candidate


def logical_skill_names(candidates: Any) -> set[str]:
    return {name for name in map(logical_skill_name, candidates) if isinstance(name, str)}


def detect_skill_candidates(text: str) -> set[str]:
    normalized = text.replace("\\", "/")
    candidates = set(re.findall(r"(?:^|/)skills/+([^/]+)/+", normalized))
    candidates.update(re.findall(_SKILL_KEY + r'([^"]+)"', normalized))
    return candidates | logical_skill_names(re.findall(_INVOKE_KEY + r'([^"]+)"', normalized))


def _tool_text(entries: Any) -> str:
    return "\n".join(
        text for role, text in entries if role == "skill" or role.startswith("tool:")
    ).replace("\\", "/")


def detect_skills_from_entries(entries: Any, skill_names: Any) -> set[str]:
    tool_text = _tool_text(entries)
    detected = detect_skill_candidates(tool_text) & set(skill_names)
    for name in skill_names:
        if f"skills/{name}/" in tool_text or f"{name}/SKILL.md" in tool_text:
            detected.add(name)
    return detected


def skill_evidence(entries: Any, name: str) -> str:
    """Rank how a transcript names a skill: path, bare_name, qualified_name, or unrecorded."""
    tool_text = _tool_text(entries)
    if f"skills/{name}/" in tool_text or f"{name}/SKILL.md" in tool_text:
        return "path"
    quoted = re.escape(name)
    if re.search(_SKILL_KEY + quoted + '"', tool_text):
        return "bare_name"
    if re.search(_INVOKE_KEY + r"[\w.-]+:" + quoted + '"', tool_text):
        return "qualified_name"
    return "unrecorded"


def skill_variants(skills: Any) -> dict[str, Any]:
    """Name every content-distinct definition. Only the edit target is a current claim."""
    return {
        name: {
            "edit_target": {"path": skill["path"], "sha256": skill["sha256"]},
            "definitions": skill["definitions"],
            "historical_attribution": "unresolved",
        }
        for name, skill in sorted(skills.items())
        if len(skill["definitions"]) > 1
    }


def _attribution(entries: Any, used: Any, variants: Any) -> dict[str, Any]:
    """Flag usage whose executed definition cannot be known from the transcript."""
    notes = {}
    for name in used:
        evidence = skill_evidence(entries, name)
        reasons = ["conflicting_definitions"] if name in variants else []
        if evidence == "qualified_name":
            reasons.append("namespace_unverified")
        elif evidence == "unrecorded":
            reasons.append("evidence_not_in_transcript")
        if reasons:
            notes[name] = {"evidence": evidence, "unresolved_because": reasons}
    return notes


def resolve_session_usage(sessions: Any, skills: Any) -> None:
    """Set logical usage per session, independent of which definition is the edit target."""
    installed = set(skills)
    variants = skill_variants(skills)
    for session in sessions:
        entries = session["_entries"]
        detected = detect_skills_from_entries(entries, installed)
        used = (set(session["skills_used"]) | detected) & installed
        session["skills_used"] = sorted(used)
        notes = _attribution(entries, session["skills_used"], variants)
        if notes:
            session["skill_attribution"] = notes


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


_FRACTION = re.compile(r"\.(\d+)")


def parse_session_timestamp(value: Any) -> datetime | None:
    """Return an aware UTC datetime for an ISO string or epoch number, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    # Python 3.10 fromisoformat accepts only 3 or 6 fraction digits.
    text = _FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), text, count=1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_live_session(stats: Any, min_idle_minutes: float) -> bool:
    """A session whose last record is inside the quiet window may still be running."""
    last = parse_session_timestamp(stats.get("last_ts"))
    if last is None or min_idle_minutes <= 0:
        return False
    return datetime.now(timezone.utc) - last < timedelta(minutes=min_idle_minutes)


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
        self.terminated: tuple[str, str] | None = None

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

    def terminate(self, reason: str, message: str = "") -> None:
        """Record that the provider, not the agent, ended the session.

        Each harness adapter calls this from its own record matcher. A later
        record that shows the agent still working calls `resume`.
        """
        self.terminated = (reason, message.strip())

    def resume(self) -> None:
        self.terminated = None

    def finish(self, meta: Any, edit_tools: Any = ()) -> Any:
        if self.terminated:
            reason, message = self.terminated
            self.append("terminated", f"{reason}: {message}" if message else reason)
        self.stats.update(
            first_ts=self.first_ts,
            last_ts=self.last_ts,
            has_code_edits=self.edits or bool(self.tools & set(edit_tools)),
            terminated_by=self.terminated[0] if self.terminated else None,
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
    ]
    if stats.get("terminated_by"):
        lines.append(f"- terminated by: {stats['terminated_by']} (provider ended the session)")
    lines.extend(("", "## Condensed transcript", ""))
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
