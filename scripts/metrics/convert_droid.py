#!/usr/bin/env python3
"""Convert Factory Droid CLI session transcripts into Claude Code-shaped JSONL.

The REQ-048 replay (``friction_calibration.py``) and the failure classifier
(``scripts/failure_classifier/transcript.py``) read Claude Code transcripts.
Droid is close: its ``message`` records already hold ``tool_use`` and
``tool_result`` blocks paired by id, with ``is_error`` present on results.

Droid record shapes this converter relies on (observed 2026-11-03 over the
sessions modified in the prior 31 days):

- ``{"type": "message", "timestamp", "message": {"role", "content", ...}}``;
  ``content`` is a list of ``text``, ``thinking``, ``tool_use``, and
  ``tool_result`` blocks.
- The shell tool is ``Execute`` with ``input.command``. It maps to ``Bash``.
  ``ApplyPatch`` maps to ``apply_patch`` so the classifier sees an edit tool.
- ``tool_result.is_error`` is ``true`` on failure, ``false`` or absent otherwise.
- A human turn is a ``user`` message with ``userMessageSource == "cli_tui"``,
  no ``visibility`` key, and text not opening with ``<`` (``<system-reminder>``
  blocks are injected). ``visibility`` of ``llm_only``, ``user_only``, or
  ``both`` marks injected notices, background results, and ``!`` commands.
- A subagent session opens with ``session_start.callingSessionId``. There is
  no per-record sidechain flag, so those sessions are skipped whole.
- Hook events are ``message`` records with ``hookEventName``. Stop hooks
  record ``exitCode`` 0 only in this corpus and no ``Stop hook feedback`` text
  exists, so no hook-block record is ever emitted (``hook_blocks`` stays 0).
- ``todo_state``, ``agent_turn_outcome``, ``compaction_state``, and hook
  records carry no conversation content and are dropped.

EXIT CODES (ADR-035):
    0 - Success
    2 - Invalid arguments or unsafe output directory
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if (_PROJECT_ROOT / "scripts" / "validation" / "models.py").is_file() and str(
    _PROJECT_ROOT
) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.metrics import convert_common  # noqa: E402
from scripts.metrics.friction_calibration import inside_repository  # noqa: E402

EXIT_OK = 0
EXIT_CONFIG = 2
FILE_MODE = 0o600
HUMAN_SOURCE = "cli_tui"
SHELL_TOOL = "Execute"
TOOL_RENAMES = {SHELL_TOOL: "Bash", "ApplyPatch": "apply_patch"}


@dataclass
class Stats:
    """Run totals, printed as one line."""

    files: int = 0
    sessions: int = 0
    tool_calls: int = 0
    errored_results: int = 0
    human_turns: int = 0
    hook_blocks: int = 0
    skipped: Counter[str] = field(default_factory=Counter)

    def add(self, other: Stats) -> None:
        self.tool_calls += other.tool_calls
        self.errored_results += other.errored_results
        self.human_turns += other.human_turns
        self.hook_blocks += other.hook_blocks
        self.skipped.update(other.skipped)

    def summary(self) -> str:
        skipped = ",".join(f"{k}:{v}" for k, v in sorted(self.skipped.items())) or "0"
        return (
            f"files={self.files} sessions={self.sessions} tool_calls={self.tool_calls} "
            f"errored_results={self.errored_results} human_turns={self.human_turns} "
            f"hook_blocks={self.hook_blocks} skipped={skipped}"
        )


def parse_day(value: object) -> date | None:
    """The UTC calendar day of an ISO timestamp, or None when unparsable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed).astimezone(UTC).date()


def read_records(path: Path, stats: Stats) -> Iterator[dict[str, Any]]:
    """Yield JSON object lines; count malformed lines as skipped."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (ValueError, RecursionError):
                record = None
            if isinstance(record, dict):
                yield record
            else:
                stats.skipped["bad_line"] += 1


def _content_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _tool_use(block: dict[str, Any]) -> dict[str, Any] | None:
    use_id, name = block.get("id"), block.get("name")
    if not isinstance(use_id, str) or not isinstance(name, str) or not name.strip():
        return None
    raw_input = block.get("input")
    if name == SHELL_TOOL:
        command = raw_input.get("command") if isinstance(raw_input, dict) else None
        raw_input = {"command": command if isinstance(command, str) else ""}
    return {
        "type": "tool_use",
        "id": use_id,
        "name": TOOL_RENAMES.get(name, name),
        "input": raw_input,
    }


def _human_text(message: dict[str, Any]) -> str:
    """The typed text of a user message, with injected ``<...>`` blocks removed."""
    content = message.get("content")
    if isinstance(content, str):
        parts = [content]
    else:
        parts = [b["text"] for b in _content_blocks(message) if isinstance(b.get("text"), str)]
    kept = [p for p in parts if p.strip() and not p.lstrip().startswith("<")]
    return "\n".join(kept)


def _is_human(message: dict[str, Any]) -> bool:
    return message.get("userMessageSource") == HUMAN_SOURCE and "visibility" not in message


def _assistant_record(
    ts: str, message: dict[str, Any], seen: set[str], stats: Stats
) -> dict[str, Any] | None:
    blocks: list[dict[str, Any]] = []
    for block in _content_blocks(message):
        kind = block.get("type")
        if kind == "text" and isinstance(block.get("text"), str) and block["text"].strip():
            blocks.append({"type": "text", "text": block["text"]})
        elif kind == "tool_use":
            use = _tool_use(block)
            if use is None or use["id"] in seen:
                stats.skipped["bad_tool_use"] += 1
                continue
            seen.add(use["id"])
            stats.tool_calls += 1
            blocks.append(use)
    if not blocks:
        return None
    return {"type": "assistant", "timestamp": ts, "message": {"content": blocks}}


def _result_records(ts: str, message: dict[str, Any], stats: Stats) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for block in _content_blocks(message):
        use_id = block.get("tool_use_id")
        if block.get("type") != "tool_result" or not isinstance(use_id, str):
            continue
        is_error = block.get("is_error") is True
        stats.errored_results += is_error
        result = {
            "type": "tool_result",
            "tool_use_id": use_id,
            "content": block.get("content", ""),
            "is_error": is_error,
        }
        records.append(
            {"type": "user", "timestamp": ts, "toolUseResult": {}, "message": {"content": [result]}}
        )
    return records


def _user_records(ts: str, message: dict[str, Any], stats: Stats) -> list[dict[str, Any]]:
    records = _result_records(ts, message, stats)
    if _is_human(message):
        text = _human_text(message)
        if text:
            stats.human_turns += 1
            records.append(
                {
                    "type": "user",
                    "timestamp": ts,
                    "promptSource": "typed",
                    "message": {"content": text},
                }
            )
    return records


def convert_records(records: Iterable[dict[str, Any]], stats: Stats) -> list[dict[str, Any]]:
    """Map Droid records of one session to Claude Code-shaped records, in order."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        message = record.get("message")
        if record.get("type") != "message" or not isinstance(message, dict):
            continue
        ts = record.get("timestamp")
        if not isinstance(ts, str) or not ts:
            stats.skipped["no_timestamp"] += 1
            continue
        role = message.get("role")
        if role == "assistant":
            converted = _assistant_record(ts, message, seen, stats)
            out.extend([converted] if converted else [])
        elif role == "user":
            out.extend(_user_records(ts, message, stats))
    return out


def is_subagent(records: Iterable[dict[str, Any]]) -> bool:
    return any(r.get("type") == "session_start" and r.get("callingSessionId") for r in records)


def first_day(records: Iterable[dict[str, Any]]) -> date | None:
    for record in records:
        day = parse_day(record.get("timestamp"))
        if day is not None:
            return day
    return None


def write_private(path: Path, records: list[dict[str, Any]]) -> None:
    convert_common.write_private(path, convert_common.dump_jsonl(records))


def convert_file(
    path: Path, out_dir: Path, since: date, include_subagents: bool, written: set[str]
) -> Stats:
    """Convert one Droid session file; the returned Stats holds its own totals."""
    stats = Stats()
    if convert_common.safe_session_id(path.stem) is None:
        stats.skipped["unsafe_id"] += 1
        return stats
    records = list(read_records(path, stats))
    day = first_day(records)
    if day is None or day < since:
        stats.skipped["window"] += 1
    elif is_subagent(records) and not include_subagents:
        stats.skipped["subagent"] += 1
    elif path.stem in written:
        stats.skipped["duplicate_id"] += 1
    else:
        converted = convert_records(records, stats)
        if converted:
            written.add(path.stem)
            write_private(out_dir / f"{path.stem}.jsonl", converted)
            stats.sessions = 1
        else:
            stats.skipped["empty"] += 1
    return stats


def run(src_glob: str, out_dir: Path, since: date, include_subagents: bool = False) -> Stats:
    convert_common.ensure_private_dir(out_dir)
    total = Stats()
    written: set[str] = set()
    for name in sorted(glob.glob(os.path.expanduser(src_glob))):
        part = convert_file(Path(name), out_dir, since, include_subagents, written)
        total.files += 1
        total.sessions += part.sessions
        total.add(part)
    return total


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--src-glob", required=True, help="Droid session files, e.g. DIR/*/*.jsonl")
    parser.add_argument("--out-dir", required=True, help="private directory outside any git repo")
    parser.add_argument("--since", type=_parse_date, required=True, help="first record day, UTC")
    parser.add_argument(
        "--include-subagents", action="store_true", help="also convert subagent sessions"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir).expanduser()
    if inside_repository(out_dir):
        print(f"error: --out-dir {out_dir} is inside a git repository", file=sys.stderr)
        return EXIT_CONFIG
    stats = run(args.src_glob, out_dir, args.since, args.include_subagents)
    print(stats.summary())
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
