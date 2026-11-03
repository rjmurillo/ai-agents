#!/usr/bin/env python3
"""Convert OpenAI Codex CLI rollout transcripts into Claude Code-shaped JSONL.

The friction replay (``friction_calibration.py replay``) reads Claude Code
records. This tool maps Codex ``rollout-*.jsonl`` files onto that shape so the
replay runs on them unchanged. Schema facts, observed over 979 files modified
in the 31 days before 2026-11-03:

- Atomic tool executions arrive as ``event_msg`` / ``item_completed`` items:
  ``CommandExecution`` (``command`` argv, ``aggregated_output``, ``exit_code``,
  ``status``), ``McpToolCall`` (``server``, ``tool``, ``arguments``, ``result``
  or ``error``, ``status``) and ``FileChange`` (``changes``, ``stdout``,
  ``status``). Each item's own ``id`` pairs its call with its result.
- ``response_item`` ``function_call`` / ``function_call_output`` pair by
  ``call_id`` and carry no error flag. ``custom_tool_call`` is the ``exec``
  JavaScript wrapper around the items above; it is emitted only when its
  output opens with ``Script failed`` and no item completed inside its span
  was itself an error, so a failed inner call is not counted twice.
- Human prompts are ``UserMessage`` items. Legacy sessions use ``event_msg``
  ``user_message``; sessions with neither fall back to ``response_item``
  user messages. Injected context (AGENTS.md, ``<environment_context>``) is
  never emitted as a human turn.
- ``session_meta.payload`` marks subagent threads with ``thread_source ==
  "subagent"``, a ``source.subagent`` object, or ``parent_thread_id``; forks
  carry ``forked_from_id``. Both are skipped.
- A ``HookPrompt`` item whose fragments have ``hookRunId`` starting ``stop:``
  is a Stop hook continuation prompt.

EXIT CODES (ADR-035):
    0 - Success
    2 - Invalid arguments or input
"""

from __future__ import annotations

import argparse
import glob
import json
import shlex
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if (_PROJECT_ROOT / "scripts" / "validation" / "models.py").is_file() and str(
    _PROJECT_ROOT
) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.failure_classifier.transcript import STOP_FEEDBACK_PREFIX  # noqa: E402
from scripts.metrics.convert_common import (  # noqa: E402
    dump_jsonl,
    ensure_private_dir,
    safe_session_id,
    write_private,
)
from scripts.metrics.friction_calibration import inside_repository  # noqa: E402

_SHELL_FLAGS = frozenset({"-c", "-lc", "-ic", "-ilc"})
_INJECTED_PREFIXES = ("<", "# AGENTS.md instructions")
_EXEC_WRAPPER = "exec"
_WRAPPER_FAILURE = "Script failed"
COUNTER_KEYS = ("tool_calls", "errored", "human_turns", "hook_blocks")


def _is_subagent_or_fork(meta: Mapping[str, Any]) -> bool:
    source = meta.get("source")
    return (
        meta.get("thread_source") == "subagent"
        or (isinstance(source, Mapping) and "subagent" in source)
        or bool(meta.get("parent_thread_id"))
        or bool(meta.get("forked_from_id"))
    )


def _command_text(command: object) -> str:
    """The shell script of a ``zsh -lc <script>`` argv, else the joined argv."""
    if isinstance(command, str):
        return command
    if not isinstance(command, list):
        return ""
    argv = [str(part) for part in command]
    if len(argv) >= 3 and argv[1] in _SHELL_FLAGS:
        return argv[2]
    return shlex.join(argv)


def _text_blocks(content: object) -> str:
    """Join text from a Codex content value: a string or a list of blocks."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [
        block["text"]
        for block in content
        if isinstance(block, Mapping) and isinstance(block.get("text"), str)
    ]
    return "\n".join(parts)


def _tool_pair(
    ts: str, use_id: str, name: str, tool_input: object, text: str, is_error: bool
) -> list[dict[str, Any]]:
    use = {
        "type": "assistant",
        "timestamp": ts,
        "message": {
            "content": [{"type": "tool_use", "id": use_id, "name": name, "input": tool_input}]
        },
    }
    result = {
        "type": "user",
        "timestamp": ts,
        "toolUseResult": {},
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "content": text,
                    "is_error": is_error,
                }
            ]
        },
    }
    return [use, result]


def _item_pair(ts: str, item: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Map a CommandExecution, McpToolCall, or FileChange item to a call and result."""
    kind, use_id = item.get("type"), str(item.get("id", ""))
    failed = item.get("status") == "failed"
    if kind == "CommandExecution":
        text = item.get("aggregated_output")
        command = {"command": _command_text(item.get("command"))}
        bad = failed or item.get("exit_code") not in (0, None)
        return _tool_pair(ts, use_id, "Bash", command, text if isinstance(text, str) else "", bad)
    if kind == "McpToolCall":
        error = item.get("error")
        result = item.get("result")
        text = _text_blocks(result.get("content")) if isinstance(result, Mapping) else ""
        if error:
            message = error.get("message") if isinstance(error, Mapping) else None
            text = message if isinstance(message, str) else str(error)
        name = f"mcp__{item.get('server')}__{item.get('tool')}"
        return _tool_pair(
            ts, use_id, name, item.get("arguments") or {}, text, failed or bool(error)
        )
    changes = item.get("changes")
    paths = sorted(changes) if isinstance(changes, Mapping) else []
    tool_input = {"file_path": paths[0] if paths else "", "paths": paths}
    out = item.get("stdout") or item.get("stderr") or ""
    return _tool_pair(ts, use_id, "apply_patch", tool_input, out, item.get("status") != "completed")


def _function_input(arguments: object) -> object:
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return {"arguments": arguments}
    return arguments if arguments is not None else {}


def _text_record(role: str, ts: str, text: str, **extra: str) -> dict[str, Any]:
    if role == "assistant":
        return {
            "type": "assistant",
            "timestamp": ts,
            "message": {"content": [{"type": "text", "text": text}]},
        }
    return {"type": "user", "timestamp": ts, "message": {"content": text}, **extra}


def _human_ok(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and not stripped.startswith(_INJECTED_PREFIXES)


class _Session:
    """Accumulates the records of one rollout file in source order."""

    def __init__(self) -> None:
        self.tools: list[tuple[int, dict[str, Any]]] = []
        # Candidate prose by source, in preference order. First non-empty wins.
        self.humans: dict[str, list[tuple[int, dict[str, Any]]]] = {
            "item": [],
            "event": [],
            "resp": [],
        }
        self.agents: dict[str, list[tuple[int, dict[str, Any]]]] = {"item": [], "resp": []}
        self.hooks: list[tuple[int, dict[str, Any]]] = []
        self.calls: dict[str, tuple[str, str, object, int]] = {}

    def add_pair(self, idx: int, pair: list[dict[str, Any]]) -> None:
        self.tools.extend((idx, rec) for rec in pair)

    def handle(self, idx: int, record: Mapping[str, Any]) -> None:
        ts, payload = record.get("timestamp"), record.get("payload")
        if not isinstance(ts, str) or not isinstance(payload, Mapping):
            return
        kind = payload.get("type")
        if record.get("type") == "event_msg":
            self._event(idx, ts, kind, payload)
        elif record.get("type") == "response_item":
            self._response(idx, ts, kind, payload)

    def _event(self, idx: int, ts: str, kind: object, payload: Mapping[str, Any]) -> None:
        if kind == "user_message" and isinstance(payload.get("message"), str):
            self._human("event", idx, ts, payload["message"])
        item = payload.get("item")
        if kind != "item_completed" or not isinstance(item, Mapping):
            return
        item_type = item.get("type")
        if item_type in ("CommandExecution", "McpToolCall", "FileChange"):
            self.add_pair(idx, _item_pair(ts, item))
        elif item_type == "UserMessage":
            self._human("item", idx, ts, _text_blocks(item.get("content")))
        elif item_type == "AgentMessage":
            self._agent("item", idx, ts, _text_blocks(item.get("content")))
        elif item_type == "HookPrompt":
            self._hook(idx, ts, item)

    def _hook(self, idx: int, ts: str, item: Mapping[str, Any]) -> None:
        fragments = item.get("fragments")
        if not isinstance(fragments, list):
            return
        stops = [
            f["text"]
            for f in fragments
            if isinstance(f, Mapping)
            and isinstance(f.get("text"), str)
            and str(f.get("hookRunId", "")).startswith("stop:")
        ]
        if stops:
            text = f"{STOP_FEEDBACK_PREFIX}\n" + "\n".join(stops)
            self.hooks.append((idx, _text_record("user", ts, text)))

    def _response(self, idx: int, ts: str, kind: object, payload: Mapping[str, Any]) -> None:
        if kind == "message":
            text = _text_blocks(payload.get("content"))
            if payload.get("role") == "user":
                self._human("resp", idx, ts, text)
            elif payload.get("role") == "assistant":
                self._agent("resp", idx, ts, text)
        elif kind in ("function_call", "custom_tool_call"):
            call_id, name = payload.get("call_id"), payload.get("name")
            raw = payload.get("arguments" if kind == "function_call" else "input")
            if isinstance(call_id, str) and isinstance(name, str):
                self.calls[call_id] = (kind, name, raw, len(self.tools))
        elif kind in ("function_call_output", "custom_tool_call_output"):
            self._output(idx, ts, kind, payload)

    def _output(self, idx: int, ts: str, kind: object, payload: Mapping[str, Any]) -> None:
        call_id = payload.get("call_id")
        call = self.calls.pop(call_id, None) if isinstance(call_id, str) else None
        if call is None:
            return
        _, name, raw, start = call
        text = _text_blocks(payload.get("output"))
        if kind == "custom_tool_call_output":
            if name != _EXEC_WRAPPER or not text.startswith(_WRAPPER_FAILURE):
                return
            if self._inner_errored(start):
                return
            self.add_pair(idx, _tool_pair(ts, str(call_id), name, {"code": raw}, text, True))
            return
        self.add_pair(idx, _tool_pair(ts, str(call_id), name, _function_input(raw), text, False))

    def _inner_errored(self, start: int) -> bool:
        """True when an item completed inside a wrapper's span was itself an error.

        Codex records no parent id from an inner call to its wrapper, so the
        span is every tool result since the wrapper's call. A failing sibling
        call can hide a real wrapper failure (a possible undercount).
        """
        for _, rec in self.tools[start:]:
            content = rec.get("message", {}).get("content")
            first = content[0] if isinstance(content, list) and content else {}
            if first.get("is_error") is True:
                return True
        return False

    def _human(self, source: str, idx: int, ts: str, text: str) -> None:
        if _human_ok(text):
            self.humans[source].append((idx, _text_record("user", ts, text, promptSource="typed")))

    def _agent(self, source: str, idx: int, ts: str, text: str) -> None:
        if text.strip():
            self.agents[source].append((idx, _text_record("assistant", ts, text)))

    def records(self) -> list[dict[str, Any]]:
        humans = next((v for v in self.humans.values() if v), [])
        agents = next((v for v in self.agents.values() if v), [])
        merged = sorted(self.tools + humans + agents + self.hooks, key=lambda pair: pair[0])
        return [rec for _, rec in merged]


def convert_lines(lines: Iterable[str]) -> tuple[str | None, str, list[dict[str, Any]]]:
    """Convert one rollout. Returns (skip reason or None, session id, records)."""
    session = _Session()
    session_id = ""
    for idx, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, Mapping):
            continue
        payload = record.get("payload")
        if record.get("type") == "session_meta" and isinstance(payload, Mapping) and not session_id:
            if _is_subagent_or_fork(payload):
                return "subagent_or_fork", str(payload.get("id", "")), []
            session_id = str(payload.get("id", ""))
        session.handle(idx, record)
    return None, session_id, session.records()


def _count(records: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for rec in records:
        content = rec.get("message", {}).get("content")
        first = content[0] if isinstance(content, list) and content else {}
        counts["tool_calls"] += int(first.get("type") == "tool_use")
        counts["errored"] += int(first.get("is_error") is True)
        counts["human_turns"] += int(rec.get("promptSource") == "typed")
        counts["hook_blocks"] += int(
            isinstance(content, str) and content.startswith(STOP_FEEDBACK_PREFIX)
        )
    return counts


def _write(path: Path, records: list[dict[str, Any]]) -> None:
    write_private(path, dump_jsonl(records))


def convert_files(paths: Iterable[str], out_dir: Path, since: date) -> Counter[str]:
    totals: Counter[str] = Counter()
    used: set[str] = set()
    for path in paths:
        totals["files"] += 1
        with open(path, encoding="utf-8", errors="replace") as handle:
            reason, session_id, records = convert_lines(handle)
        if reason or not records or records[0]["timestamp"][:10] < since.isoformat():
            totals["skipped"] += 1
            totals[f"skipped_{reason or 'empty_or_before_since'}"] += 1
            continue
        # A rollout with no session_meta id falls back to its file name.
        stem = safe_session_id(session_id) or safe_session_id(Path(path).stem)
        if stem is None:
            totals["skipped"] += 1
            totals["skipped_unsafe_id"] += 1
            continue
        name, n = stem, 1
        while name in used:
            n += 1
            name = f"{stem}-{n}"
        used.add(name)
        _write(out_dir / f"{name}.jsonl", records)
        totals["sessions"] += 1
        totals.update(_count(records))
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src-glob", required=True)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    try:
        since = date.fromisoformat(args.since)
    except ValueError:
        print(f"error: invalid --since {args.since!r}", file=sys.stderr)
        return 2
    if inside_repository(args.out_dir):
        print(f"error: out dir {args.out_dir} is inside a git repository", file=sys.stderr)
        return 2
    ensure_private_dir(args.out_dir)
    totals = convert_files(sorted(glob.glob(args.src_glob, recursive=True)), args.out_dir, since)
    for key in ("files", "sessions", *COUNTER_KEYS, "skipped"):
        print(f"{key}={totals[key]}")
    for key in sorted(k for k in totals if k.startswith("skipped_")):
        print(f"{key}={totals[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
