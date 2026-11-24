"""SPIKE ONLY. Feed Claude Code session transcripts to the vendored checker core.

Not shipped, not wired to any hook. Reads one Claude Code session JSONL and
yields, per human turn, the final reply text and the tool calls made in that
turn, shaped the way the vendored core's ``evidence.extract`` expects.

Turn model:
- A turn starts at a main-thread user record that carries human text (not a
  tool result, not meta, not a sidechain record).
- The final reply is the assistant text written after the turn's last
  tool_use. A turn whose last assistant output is a tool call has no reply.
- Delegated work (Agent, delegate_task) runs in other transcripts; only the
  parent's own calls are on record here.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VENDOR = Path(__file__).resolve().parent / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from nocap.claims import extract_claims  # noqa: E402
from nocap.evidence import extract, ledger_fact  # noqa: E402
from nocap.verdict import judge  # noqa: E402

EXIT_RE = re.compile(r"^Exit code (\d+)\b")
DELEGATING_TOOLS = frozenset({"Agent", "Task", "mcp__t3-code__delegate_task"})


@dataclass
class ToolCall:
    """One tool_use with its matching tool_result."""

    name: str
    args: dict[str, Any]
    ts: float | None = None
    result_text: str = ""
    is_error: bool = False
    has_result: bool = False


@dataclass
class Turn:
    """One human prompt and everything the main thread did until the next one."""

    index: int
    calls: list[ToolCall] = field(default_factory=list)
    reply: str = ""
    delegated: bool = False


def _ts(record: dict[str, Any]) -> float | None:
    raw = record.get("timestamp")
    if not isinstance(raw, str):
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
        ]
        return "\n".join(p for p in parts if isinstance(p, str))
    return ""


def _is_human_prompt(record: dict[str, Any]) -> bool:
    if record.get("type") != "user" or record.get("isSidechain") or record.get("isMeta"):
        return False
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        kinds = {c.get("type") for c in content if isinstance(c, dict)}
        return "tool_result" not in kinds and "text" in kinds
    return False


class _TurnReader:
    """Accumulates main-thread records into turns."""

    def __init__(self) -> None:
        self.turns: list[Turn] = []
        self.pending: dict[str, ToolCall] = {}
        self.current: Turn | None = None
        self.tail_text: list[str] = []

    def close(self) -> None:
        if self.current is not None:
            self.current.reply = "\n\n".join(t for t in self.tail_text if t.strip())

    def feed(self, record: dict[str, Any]) -> None:
        if record.get("isSidechain"):
            return
        if _is_human_prompt(record):
            self.close()
            self.current = Turn(index=len(self.turns) + 1)
            self.turns.append(self.current)
            self.tail_text = []
            return
        content = (record.get("message") or {}).get("content")
        if self.current is None or not isinstance(content, list):
            return
        blocks = [b for b in content if isinstance(b, dict)]
        if record.get("type") == "assistant":
            self._assistant(self.current, blocks, _ts(record))
        elif record.get("type") == "user":
            self._results(blocks, _ts(record))

    def _assistant(self, turn: Turn, blocks: list[dict[str, Any]], ts: float | None) -> None:
        for block in blocks:
            if block.get("type") == "text":
                self.tail_text.append(str(block.get("text") or ""))
            elif block.get("type") == "tool_use":
                raw = block.get("input")
                args: dict[str, Any] = raw if isinstance(raw, dict) else {}
                call = ToolCall(name=str(block.get("name") or ""), args=args, ts=ts)
                turn.calls.append(call)
                turn.delegated = turn.delegated or call.name in DELEGATING_TOOLS
                self.pending[str(block.get("id"))] = call
                self.tail_text = []

    def _results(self, blocks: list[dict[str, Any]], ts: float | None) -> None:
        for block in blocks:
            if block.get("type") != "tool_result":
                continue
            call = self.pending.pop(str(block.get("tool_use_id")), None)
            if call is None:
                continue
            call.result_text = _result_text(block.get("content"))
            call.is_error = bool(block.get("is_error"))
            call.has_result = True
            call.ts = ts if ts is not None else call.ts


def read_turns(path: Path) -> list[Turn]:
    """Split one transcript into main-thread turns."""
    reader = _TurnReader()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                reader.feed(record)
    reader.close()
    return reader.turns


def to_core_call(call: ToolCall) -> tuple[str, dict[str, Any], dict[str, Any], str | None]:
    """Map a Claude Code tool call onto the vendored core's (name, args, result, status).

    The result is always a dict so the core never re-parses a JSON-looking stdout
    as a tool envelope (its ``code``, ``error`` and ``success`` keys would read as
    exit status).
    """
    name, args = call.name, call.args
    exit_code: int | None = None
    status: str | None = "error" if call.is_error else None
    text = call.result_text
    shell = False
    core_args: dict[str, Any]
    if name == "Bash":
        core_name, core_args, shell = "bash", {"command": str(args.get("command") or "")}, True
    elif name.endswith("ctx_execute"):
        language = str(args.get("language") or "").lower()
        core_name = "bash" if language in ("shell", "bash", "sh", "zsh") else "execute_code"
        core_args, shell = {"code": str(args.get("code") or "")}, True
    elif name in ("Edit", "MultiEdit"):
        core_name = "edit_file"
        core_args = {
            "path": args.get("file_path"),
            "old_string": args.get("old_string"),
            "new_string": args.get("new_string"),
        }
        if name == "MultiEdit" and isinstance(args.get("edits"), list):
            edits = [e for e in args["edits"] if isinstance(e, dict)]
            core_args["old_string"] = "\n".join(str(e.get("old_string") or "") for e in edits)
            core_args["new_string"] = "\n".join(str(e.get("new_string") or "") for e in edits)
    elif name == "Write":
        core_name, core_args = (
            "write_file",
            {"path": args.get("file_path"), "content": args.get("content")},
        )
    elif name == "Read":
        core_name, core_args = "read_file", {"path": args.get("file_path")}
    else:
        core_name, core_args = name, dict(args)
    if shell and call.has_result:
        match = EXIT_RE.match(text) if call.is_error else None
        if match:
            exit_code, status = int(match.group(1)), None
            text = text[match.end() :].lstrip("\n")
        elif not call.is_error:
            exit_code = 0
    return core_name, core_args, {"output": text, "exit_code": exit_code}, status


def turn_evidence(turn: Turn, cwd: str = "") -> list[dict[str, Any]]:
    """Run the core's per-call extractor over one turn, stamping transcript time."""
    out: list[dict[str, Any]] = []
    for i, call in enumerate(turn.calls, 1):
        name, args, result, status = to_core_call(call)
        ev = extract(name, args, result, status=status, index=i, cwd=cwd)
        if call.ts is not None:
            ev["ts"] = round(call.ts, 3)
        out.append(ev)
    return out


@dataclass
class TurnVerdicts:
    """Claims and receipts for one turn's final reply."""

    turn: int
    delegated: bool
    calls: int
    claims: list[dict[str, Any]]
    receipts: list[dict[str, Any]]


def check_transcript(path: Path, cwd: str = "") -> Iterator[TurnVerdicts]:
    """Judge every turn's final reply, carrying session history across turns like engine.py."""
    history: list[dict[str, Any]] = []
    for turn in read_turns(path):
        evs = turn_evidence(turn, cwd=cwd)
        reply = turn.reply
        if reply.strip():
            claims = extract_claims(reply)
            receipts = (
                judge(claims, evs, history=history, turn=turn.index, reply=reply) if claims else []
            )
            yield TurnVerdicts(turn.index, turn.delegated, len(turn.calls), claims, receipts)
        history.append(
            {"turn": turn.index, "turn_id": str(turn.index), "calls": [ledger_fact(e) for e in evs]}
        )
