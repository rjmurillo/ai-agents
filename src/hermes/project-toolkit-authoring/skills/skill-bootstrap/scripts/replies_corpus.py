"""Parse Claude Code session transcripts into turns for reply-friction sampling.

Local use only. Nothing in this module prints transcript text.

A "reply" is the assistant text emitted after the last tool boundary of a span
(the stretch between two user turns). Text written before a tool call is
progress narration, not a reply. A span that ends in an API error, or in a
failed tool result with no text after it, yields an "error" turn instead.

Transcript shape assumed (verified only against synthetic fixtures): one JSON
object per line with `type` of `user` or `assistant`, a `message.content`
string or block list, `timestamp`, and the optional flags `isSidechain`,
`isMeta`, `isCompactSummary`, `isApiErrorMessage`. Subagent transcripts live in
`<session id>/subagents/**/*.jsonl` beside the parent, with an optional
`<name>.meta.json` sibling.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 256 * 1024 * 1024
HOST_CONTINUE = "Continue where you left off."
INTERRUPT = "[Request interrupted by user"
NOTICE_PREFIXES = (
    "<task-notification",
    "<command-name>",
    "<command-message>",
    "<local-command",
    "<bash-input>",
    "<bash-stdout>",
    "<system-reminder>",
    "Caveat:",
    "This session is being continued",
    "<user-prompt-submit-hook>",
    "<teammate-message",
    "<agent-message",
    "<tool-use-rejected",
)
TAG_BLOCK = re.compile(
    r"<(system-reminder|hindsight_memory|hindsight_knowledge|pasted_content[^>]*|"
    r"retrospective-guide|claude-mem-context|task-notification|local-command-stdout|"
    r"command-name|command-message|command-args)>.*?</\1>",
    re.S,
)
AGENT_TYPE = re.compile(r"[\w.\-]{1,40}")


class ConfigError(Exception):
    """A usage or configuration problem. The message is a fixed code, never transcript text."""


@dataclass(frozen=True)
class Source:
    path: Path
    sid: str
    parent: str | None
    child: bool


@dataclass
class Turn:
    role: str  # human | machine | reply | error | interrupt
    ts: str | None
    text: str = ""
    reason: str = ""


@dataclass
class Transcript:
    src: Source
    first: str | None = None
    last: str | None = None
    turns: list[Turn] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)
    parse_errors: int = 0
    entrypoint: str | None = None


@dataclass
class _Span:
    pending: list[str] = field(default_factory=list)
    message_id: str | None = None
    tools: int = 0
    last_ts: str | None = None
    api_error: bool = False
    tool_error: bool = False


def parse_ts(value: Any) -> datetime | None:
    """Parse an ISO timestamp; a naive value is read as UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def discover(store: Path) -> list[Source]:
    """List the session and subagent transcripts of one explicit project directory."""
    if not store.is_dir():
        raise ConfigError("store_not_a_directory")
    mains = sorted(p for p in store.glob("*.jsonl") if p.is_file() and not p.is_symlink())
    if not mains:
        raise ConfigError(
            "store_looks_like_root" if any(store.glob("*/*.jsonl")) else "store_has_no_sessions"
        )
    found = [Source(p, p.stem, None, False) for p in mains]
    for parent in mains:
        sub = store / parent.stem / "subagents"
        if not sub.is_symlink() and not sub.parent.is_symlink() and sub.is_dir():
            kids = sorted(c for c in sub.rglob("*.jsonl") if c.is_file() and not c.is_symlink())
            found += [Source(c, c.stem, parent.stem, True) for c in kids]
    return found


def read_meta(src: Source) -> tuple[bool, str | None, bool | None]:
    """Return (meta file present, agent type, finished). Only a short identifier is kept."""
    meta = src.path.with_suffix(".meta.json")
    if not src.child or not meta.is_file() or meta.is_symlink():
        return False, None, None
    try:
        data = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return True, None, None
    if not isinstance(data, dict):
        return True, None, None
    kind, done = data.get("agentType"), data.get("finished")
    named = isinstance(kind, str) and AGENT_TYPE.fullmatch(kind) is not None
    return True, kind if named else None, done if isinstance(done, bool) else None


def split_content(content: Any) -> tuple[str, list[bool]]:
    """Return (joined text, is_error flag per tool_result block)."""
    if isinstance(content, str):
        return content, []
    parts: list[str] = []
    results: list[bool] = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block.get("type") == "tool_result":
            results.append(block.get("is_error") is True)
    return "\n".join(parts), results


class _Parser:
    def __init__(self, src: Source) -> None:
        self.tr = Transcript(src)
        self.span = _Span()

    def feed(self, rec: dict[str, Any]) -> None:
        kind = rec.get("type")
        if kind not in ("user", "assistant"):
            return
        if rec.get("isSidechain") and not self.tr.src.child:
            return
        entry = rec.get("entrypoint")
        if self.tr.entrypoint is None and isinstance(entry, str) and AGENT_TYPE.fullmatch(entry):
            self.tr.entrypoint = entry
        ts = rec["timestamp"] if isinstance(rec.get("timestamp"), str) else None
        if ts:
            self.tr.first = self.tr.first or ts
            self.tr.last = ts
        msg = rec.get("message")
        msg = msg if isinstance(msg, dict) else {}
        if kind == "assistant":
            self._assistant(rec, msg, ts)
        else:
            self._user(rec, msg, ts)

    def _assistant(self, rec: dict[str, Any], msg: dict[str, Any], ts: str | None) -> None:
        span = self.span
        span.last_ts = ts or span.last_ts
        if rec.get("isApiErrorMessage"):
            span.api_error = True
            span.pending.clear()
            return
        mid = msg.get("id") or rec.get("uuid")
        if isinstance(mid, str) and mid != span.message_id:
            span.pending.clear()
            span.message_id = mid
        content = msg.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if block.get("type") == "text" and isinstance(text, str) and text.strip():
                if not span.pending or span.pending[-1] != text:
                    span.pending.append(text)
            elif block.get("type") == "tool_use":
                span.pending.clear()
                span.tools += 1
                span.tool_error = False

    def _user(self, rec: dict[str, Any], msg: dict[str, Any], ts: str | None) -> None:
        text, results = split_content(msg.get("content"))
        for is_error in results:
            self.span.tool_error = is_error
        if results and not text.strip():
            return
        if INTERRUPT in text:
            self.span = _Span()
            self.tr.turns.append(Turn("interrupt", ts))
            return
        reason = _skip_reason(rec, text)
        human = TAG_BLOCK.sub("", text).strip()
        if reason or not human:
            self.tr.skipped[reason or "empty"] += 1
            return
        self._flush()
        role, why = _classify(human, self.tr.src.child)
        self.tr.turns.append(Turn(role, ts, human, why))

    def _flush(self) -> None:
        span = self.span
        if span.pending:
            self.tr.turns.append(Turn("reply", span.last_ts, "\n".join(span.pending)))
        elif span.api_error:
            self.tr.turns.append(Turn("error", span.last_ts, reason="api"))
        elif span.tool_error and span.tools:
            self.tr.turns.append(Turn("error", span.last_ts, reason="tool"))
        self.span = _Span()

    def finish(self) -> Transcript:
        self._flush()
        return self.tr


def _skip_reason(rec: dict[str, Any], text: str) -> str:
    if rec.get("isMeta"):
        return "meta"
    if rec.get("isCompactSummary"):
        return "compact_summary"
    if text.lstrip().startswith(NOTICE_PREFIXES):
        return "notice"
    return ""


def _classify(text: str, child: bool) -> tuple[str, str]:
    """Heuristic human or machine call for one user text turn."""
    if child:
        return "machine", "delegated_prompt"
    if text.startswith(HOST_CONTINUE):
        return "machine", "host_continue"
    return "human", ""


def parse_transcript(src: Source) -> Transcript:
    """Parse one transcript file into turns. Raises OSError when unreadable."""
    parser = _Parser(src)
    with src.path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if '"user"' not in line and '"assistant"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                parser.tr.parse_errors += 1
                continue
            if isinstance(rec, dict):
                parser.feed(rec)
    return parser.finish()
