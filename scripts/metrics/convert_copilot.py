"""Convert GitHub Copilot CLI session transcripts into Claude Code-shaped JSONL.

The friction replay (``friction_calibration.py replay``) reads Claude Code
transcript records. This converter lets it read Copilot CLI sessions unchanged.

Copilot CLI source shape, observed in ``~/.copilot/session-state/<id>/events.jsonl``
(388 sessions modified in the 31 days before 2026-11-03):

- every line is ``{"type", "data", "id", "timestamp", "parentId"}``;
- ``tool.execution_start`` carries ``toolCallId``, ``toolName``, ``arguments``;
- ``tool.execution_complete`` carries the same ``toolCallId`` and ``success``.
  On success, ``result.content`` holds the text. On failure, ``error`` holds
  ``{"code", "message"}``. ``code`` is ``denied`` for a permission denial and
  ``failure`` otherwise. A shell call also carries ``shellExecution.exitCode``;
- ``user.message`` ``data.content`` is the typed prompt. ``transformedContent``
  is the prompt wrapped with injected context and is never emitted;
- ``assistant.message`` ``data.content`` is agent prose (empty on a tool turn);
- ``system.message``, ``system.notification``, and ``hook.*`` events are
  injected content, not human turns.

Mapping decisions:

- A shell tool (``bash``, ``powershell``, ``shell``) becomes ``Bash`` with input
  ``{"command": ...}``. Other tools keep their Copilot name and arguments.
- Result text is copied exactly as Copilot wrote it, never rewritten.
- A blocking stop hook becomes a ``Stop hook feedback:`` user record only when a
  ``hook.end`` for ``agentStop`` carries ``output`` with ``decision == "block"``
  and a non-empty string ``reason``. No event in the observed corpus has an
  ``output`` on ``agentStop`` (all 124 end with only ``success: true``), so the
  field is a documented-contract guess that this corpus never exercises.
- Copilot records no sidechain marker, so ``isSidechain`` is never emitted.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.failure_classifier.transcript import STOP_FEEDBACK_PREFIX  # noqa: E402
from scripts.metrics.convert_common import safe_session_id, write_private  # noqa: E402
from scripts.metrics.friction_calibration import inside_repository  # noqa: E402

SHELL_TOOLS: frozenset[str] = frozenset({"bash", "powershell", "shell"})
STOP_HOOK_TYPES: frozenset[str] = frozenset({"agentStop"})

EXIT_OK = 0
EXIT_CONFIG = 2


@dataclass
class Counts:
    files: int = 0
    sessions: int = 0
    tool_calls: int = 0
    errored: int = 0
    human_turns: int = 0
    hook_blocks: int = 0
    skipped: int = 0

    def add(self, other: Counts) -> None:
        self.files += other.files
        self.sessions += other.sessions
        self.tool_calls += other.tool_calls
        self.errored += other.errored
        self.human_turns += other.human_turns
        self.hook_blocks += other.hook_blocks
        self.skipped += other.skipped


def _data(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _text_record(role: str, ts: str, text: str) -> dict[str, Any]:
    return {
        "type": role,
        "timestamp": ts,
        "message": {"content": [{"type": "text", "text": text}]},
    }


def _tool_input(name: str, arguments: object) -> object:
    """Shell tools collapse to ``{"command": str}``; others keep their arguments."""
    if name.strip().lower() not in SHELL_TOOLS:
        return arguments
    command = arguments.get("command") if isinstance(arguments, dict) else None
    return {"command": command if isinstance(command, str) else ""}


def _tool_use_record(event: dict[str, Any], ts: str) -> dict[str, Any] | None:
    data = _data(event)
    call_id, name = data.get("toolCallId"), data.get("toolName")
    if not isinstance(call_id, str) or not isinstance(name, str) or not name.strip():
        return None
    mapped = "Bash" if name.strip().lower() in SHELL_TOOLS else name
    block = {
        "type": "tool_use",
        "id": call_id,
        "name": mapped,
        "input": _tool_input(name, data.get("arguments", {})),
    }
    return {"type": "assistant", "timestamp": ts, "message": {"content": [block]}}


def _result_text(data: dict[str, Any]) -> str:
    """The text Copilot wrote: ``error.message`` on failure, else ``result.content``."""
    error = data.get("error")
    message = error.get("message") if isinstance(error, dict) else None
    if isinstance(message, str):
        return message
    result = data.get("result")
    content = result.get("content") if isinstance(result, dict) else None
    return content if isinstance(content, str) else ""


def _tool_result_record(event: dict[str, Any], ts: str) -> tuple[dict[str, Any], bool] | None:
    data = _data(event)
    call_id = data.get("toolCallId")
    if not isinstance(call_id, str):
        return None
    errored = data.get("success") is False
    block = {
        "type": "tool_result",
        "tool_use_id": call_id,
        "content": _result_text(data),
        "is_error": errored,
    }
    record = {
        "type": "user",
        "timestamp": ts,
        "toolUseResult": {},
        "message": {"content": [block]},
    }
    return record, errored


def _human_record(event: dict[str, Any], ts: str) -> dict[str, Any] | None:
    """A typed prompt: ``data.content`` only, never ``transformedContent``."""
    content = _data(event).get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return {
        "type": "user",
        "timestamp": ts,
        "promptSource": "typed",
        "message": {"content": content},
    }


def _stop_block_reason(event: dict[str, Any]) -> str | None:
    """The reason text when a stop hook's ``output`` blocks the stop, else None."""
    data = _data(event)
    if data.get("hookType") not in STOP_HOOK_TYPES:
        return None
    output = data.get("output")
    if not isinstance(output, dict) or output.get("decision") != "block":
        return None
    reason = output.get("reason")
    return reason if isinstance(reason, str) and reason.strip() else None


def _hook_block_record(event: dict[str, Any], ts: str) -> dict[str, Any] | None:
    reason = _stop_block_reason(event)
    if reason is None:
        return None
    return {
        "type": "user",
        "timestamp": ts,
        "message": {"content": f"{STOP_FEEDBACK_PREFIX} {reason}"},
    }


def convert_events(events: Iterable[object]) -> tuple[list[dict[str, Any]], Counts]:
    """Convert decoded Copilot events to Claude Code-shaped records, in order.

    Events that are not objects, or lack a string ``timestamp``, are skipped.
    """
    records: list[dict[str, Any]] = []
    counts = Counts()
    for event in events:
        if not isinstance(event, dict):
            counts.skipped += 1
            continue
        ts = event.get("timestamp")
        if not isinstance(ts, str) or not ts:
            counts.skipped += 1
            continue
        _convert_one(event, ts, records, counts)
    return records, counts


def _convert_one(
    event: dict[str, Any], ts: str, records: list[dict[str, Any]], counts: Counts
) -> None:
    kind = event.get("type")
    if kind == "user.message":
        record = _human_record(event, ts)
        counts.human_turns += record is not None
    elif kind == "assistant.message":
        content = _data(event).get("content")
        text = content if isinstance(content, str) and content.strip() else None
        record = _text_record("assistant", ts, text) if text is not None else None
    elif kind == "tool.execution_start":
        record = _tool_use_record(event, ts)
        counts.tool_calls += record is not None
    elif kind == "tool.execution_complete":
        paired = _tool_result_record(event, ts)
        record = paired[0] if paired else None
        counts.errored += bool(paired and paired[1])
    elif kind == "hook.end":
        record = _hook_block_record(event, ts)
        counts.hook_blocks += record is not None
    else:
        record = None
    if record is not None:
        records.append(record)


def _iter_events(path: Path, counts: Counts) -> Iterator[object]:
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except (ValueError, RecursionError):
                counts.skipped += 1


def _session_id(path: Path) -> str | None:
    """The parent directory name, which Copilot sets to the session id."""
    name = path.parent.name
    return safe_session_id(name)


def _first_date(records: list[dict[str, Any]]) -> date | None:
    for record in records:
        try:
            return datetime.fromisoformat(record["timestamp"]).astimezone(UTC).date()
        except (ValueError, KeyError):
            continue
    return None


def convert_file(path: Path, out_dir: Path, since: date) -> Counts:
    """Convert one session file; write ``<session id>.jsonl`` when in the window."""
    total = Counts(files=1)
    # A session cannot hold an event newer than its file's mtime, so an old
    # file cannot start inside the window. This skips reading ~10k old files.
    if datetime.fromtimestamp(path.stat().st_mtime, UTC).date() < since:
        total.skipped += 1
        return total
    scan = Counts()
    events = list(_iter_events(path, scan))
    records, counts = convert_events(events)
    counts.skipped += scan.skipped
    session_id = _session_id(path)
    started = _first_date(records)
    if session_id is None or started is None or started < since or not records:
        total.skipped += counts.skipped + 1
        return total
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    write_private(out_dir / f"{session_id}.jsonl", body)
    counts.files, counts.sessions = 1, 1
    return counts


def run(src_glob: str, out_dir: Path, since: date) -> Counts:
    out_dir.mkdir(parents=True, exist_ok=True)
    total = Counts()
    for name in sorted(glob.glob(os.path.expanduser(src_glob))):
        path = Path(name)
        if path.is_file():
            total.add(convert_file(path, out_dir, since))
    return total


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src-glob", required=True, help="glob of Copilot events.jsonl files")
    parser.add_argument("--out-dir", required=True, type=Path, help="private output directory")
    parser.add_argument("--since", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if inside_repository(args.out_dir):
        print(f"error: out dir {args.out_dir} is inside a git repository", file=sys.stderr)
        return EXIT_CONFIG
    counts = run(args.src_glob, args.out_dir, args.since)
    print(
        f"files={counts.files} sessions={counts.sessions} tool_calls={counts.tool_calls} "
        f"errored_results={counts.errored} human_turns={counts.human_turns} "
        f"hook_block_records={counts.hook_blocks} skipped={counts.skipped}"
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
