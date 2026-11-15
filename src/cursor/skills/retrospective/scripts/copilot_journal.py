"""Bounded execution receipts from an explicit native Copilot CLI journal.

``extract_evidence.py`` calls this module when the user names a Copilot
``events.jsonl`` journal with ``--journal``. The journal is the execution
source. Git history stays corroboration.

Reuse: event de-duplication, subagent filtering and the repository-scope test
come from the sibling ``skill-doctor`` scripts. This module does not call
``parse_copilot_session``, because that parser keeps prompt, assistant and
tool-result text. A receipt is an allowlist of fields: tool name, call id,
outcome, a short error code, the argument shape, and a timestamp. No prompt,
instruction, reasoning, argument value or result content is read into the
output.

Different from skill-doctor: ``session_common.iter_jsonl_records`` decodes every
line before any budget applies and swallows a mid-read ``OSError``. This module
reads lines itself so it can cap raw lines and line length first and report a
read failure. The working directory of a context event is ``cwd``, else
``gitRoot``, the same pick as ``_copilot_context`` in skill-doctor's
``session_json.py``; ``test_recorded_cwd_matches_skill_doctor`` pins it.

Safety contract:
  * Only the path the caller passes is read. Nothing is discovered or globbed.
  * Every working directory the journal records must sit inside the selected
    repository. A journal with no recorded working directory fails closed.
  * An unreadable, truncated, out-of-scope or receipt-free journal is reported
    as unavailable with a reason, never as success. A truncated journal cannot
    show that the unread part stayed in scope.
  * Reads and output are capped, and the report states caps and skipped records.
  * Nothing is written. No toolkit session log is created (issue #5228).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO

SOURCE_LABEL = "copilot-cli native journal (explicit path)"
MAX_RECEIPTS = 200
MAX_RECORDS = 100_000
MAX_LINES = 200_000
MAX_LINE_CHARS = 1_000_000
_MAX_FIELD_CHARS = 120
_CONTEXT_EVENTS = ("session.start", "session.context_changed")


def _doctor_scripts_dir() -> Path:
    """Return the sibling skill-doctor scripts directory in this plugin root."""
    return Path(__file__).resolve().parents[2] / "skill-doctor" / "scripts"


def _load_doctor() -> tuple[Any, Any] | None:
    """Import the skill-doctor modules lazily; None when the sibling is absent.

    The guarded import lets this module load in a plugin root that ships no
    skill-doctor, and the caller reports the journal as unavailable.
    """
    scripts = _doctor_scripts_dir()
    if not scripts.is_dir():
        return None
    if str(scripts) not in sys.path:
        sys.path.append(str(scripts))
    try:
        import session_discovery
        import session_json
    except ImportError:
        return None
    return session_discovery, session_json


def _clean(value: object) -> str | None:
    """Return a printable, length-bounded string for a str or int, else None."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = "".join(ch for ch in str(value) if ch.isprintable())
    return text[:_MAX_FIELD_CHARS] or None


def _call_key(value: object) -> str | None:
    """Return the full call id used to match a start with its completion.

    The id is never shortened here: two ids that share a prefix stay two calls.
    ``_clean`` shortens only what is displayed.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    return str(value) or None


def _argument_kind(arguments: object) -> str:
    """Name the shape of a tool's arguments without reading any value."""
    if arguments is None:
        return "none"
    if isinstance(arguments, str):
        return "string"
    if isinstance(arguments, dict):
        return "object"
    if isinstance(arguments, list):
        return "array"
    if isinstance(arguments, (bool, int, float)):
        return "scalar"
    return "other"


def _unavailable(path: str, reason: str, **counts: Any) -> dict[str, Any]:
    return {
        "source": SOURCE_LABEL,
        "path": path,
        "available": False,
        "reason": reason,
        "receipts": [],
        **counts,
    }


def _start_receipt(obj: dict[str, Any], key: str) -> dict[str, Any]:
    data = obj["data"]
    return {
        "tool": _clean(data.get("toolName")) or "unknown",
        "call_id": _clean(key) or "unknown",
        "outcome": "no_completion",
        "success": None,
        "error_code": None,
        "argument_kind": _argument_kind(data.get("arguments")),
        "started_at": _clean(obj.get("timestamp")),
    }


def _complete_receipt(receipt: dict[str, Any], data: dict[str, Any]) -> None:
    success = data.get("success")
    success = success if isinstance(success, bool) else None
    error = data.get("error")
    receipt["success"] = success
    receipt["error_code"] = _clean(error.get("code")) if isinstance(error, dict) else None
    receipt["outcome"] = {True: "succeeded", False: "failed"}.get(success, "unknown")


def _recorded_cwd(data: dict[str, Any]) -> str | None:
    """Return the one working directory a context event records: cwd, else gitRoot."""
    context = data.get("context", data)
    if not isinstance(context, dict):
        return None
    directory = context.get("cwd") or context.get("gitRoot")
    return directory if isinstance(directory, str) and directory else None


class _Reader:
    """Read JSON object records under a line budget, a length cap and a record cap."""

    def __init__(self) -> None:
        self.lines = self.records_read = self.malformed = self.oversized = 0
        self.truncated = False
        self.failure: str | None = None

    def records(self, path: Path) -> Iterator[dict[str, Any]]:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                yield from self._lines(stream)
        except OSError as exc:
            self.failure = type(exc).__name__

    def _lines(self, stream: TextIO) -> Iterator[dict[str, Any]]:
        while True:
            line = stream.readline(MAX_LINE_CHARS + 1)
            if not line:
                return
            if self.lines >= MAX_LINES:
                self.truncated = True
                return
            self.lines += 1
            if len(line) > MAX_LINE_CHARS and not line.endswith("\n"):
                self._skip_rest_of_line(stream)
                self.oversized += 1
                continue
            record = self._decode(line)
            if record is None:
                continue
            if self.records_read >= MAX_RECORDS:
                self.truncated = True
                return
            self.records_read += 1
            yield record

    def _decode(self, line: str) -> dict[str, Any] | None:
        if not line.strip():
            return None
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            record = None
        if not isinstance(record, dict):
            self.malformed += 1
            return None
        return record

    @staticmethod
    def _skip_rest_of_line(stream: TextIO) -> None:
        while True:
            chunk = stream.readline(MAX_LINE_CHARS)
            if not chunk or chunk.endswith("\n"):
                return


class _Collector:
    """Accumulate receipts and recorded working directories from journal events."""

    def __init__(self) -> None:
        self.receipts: dict[str, dict[str, Any]] = {}
        self.cwds: list[str] = []
        self.used = self.starts = self.no_call_id = self.unmatched = 0
        self.capped = False

    def feed(self, obj: dict[str, Any]) -> None:
        self.used += 1
        kind, data = obj.get("type"), obj["data"]
        if kind in _CONTEXT_EVENTS:
            cwd = _recorded_cwd(data)
            if cwd is not None:
                self.cwds.append(cwd)
        elif kind == "tool.execution_start":
            self._start(obj)
        elif kind == "tool.execution_complete":
            receipt = self.receipts.get(_call_key(data.get("toolCallId")) or "")
            if receipt is None:
                self.unmatched += 1
            else:
                _complete_receipt(receipt, data)

    def _start(self, obj: dict[str, Any]) -> None:
        self.starts += 1
        key = _call_key(obj["data"].get("toolCallId"))
        if key is None:
            self.no_call_id += 1
        elif key in self.receipts:
            return
        elif len(self.receipts) < MAX_RECEIPTS:
            self.receipts[key] = _start_receipt(obj, key)
        else:
            self.capped = True


def _collect(path: Path, parser: Any) -> tuple[_Reader, _Collector]:
    reader, found = _Reader(), _Collector()
    records = reader.records(path)
    for obj in parser._copilot_events(records, False):
        found.feed(obj)
    records.close()
    return reader, found


def _counts(reader: _Reader, found: _Collector) -> dict[str, Any]:
    return {
        "lines_read": reader.lines,
        "lines_cap": MAX_LINES,
        "oversized_lines": reader.oversized,
        "records_read": reader.records_read,
        "records_cap": MAX_RECORDS,
        "records_truncated": reader.truncated,
        "malformed_lines": reader.malformed,
        "records_filtered": reader.records_read - found.used,
        "tool_starts": found.starts,
        "starts_without_call_id": found.no_call_id,
        "completions_without_retained_start": found.unmatched,
        "receipts_cap": MAX_RECEIPTS,
        "receipts_truncated": found.capped,
    }


def _refusal(reader: _Reader, found: _Collector, discovery: Any, repo: Path) -> str | None:
    """Return why the journal cannot be trusted as in-scope evidence, else None."""
    if reader.failure is not None:
        return f"journal read failed: {reader.failure}"
    if reader.truncated:
        return "journal exceeds the read cap; scope of the unread part not confirmed"
    if reader.oversized:
        # A skipped line is never decoded, so it could be a context change that
        # names a directory outside the repository. Fail closed.
        return (
            f"journal has {reader.oversized} line(s) over the length cap; "
            "scope of the skipped records not confirmed"
        )
    if not found.cwds:
        return "journal records no working directory; scope not confirmed"
    if not all(discovery.session_cwd_within_repo(cwd, repo) for cwd in found.cwds):
        return "journal records a working directory outside the repository"
    if not found.receipts:
        return "journal holds no tool execution records"
    return None


def extract_receipts(journal: Path, project_dir: Path) -> dict[str, Any]:
    """Return a bounded receipt report for ``journal`` within ``project_dir``.

    The report always carries ``available`` and, when False, a ``reason``.
    """
    label = str(journal)
    doctor = _load_doctor()
    if doctor is None:
        return _unavailable(label, "skill-doctor parser unavailable in this plugin root")
    discovery, parser = doctor
    try:
        resolved = journal.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return _unavailable(label, f"journal not readable: {type(exc).__name__}")
    if not resolved.is_file():
        return _unavailable(str(resolved), "journal path is not a regular file")

    reader, found = _collect(resolved, parser)
    counts = _counts(reader, found)
    reason = _refusal(reader, found, discovery, project_dir.resolve())
    if reason is not None:
        return _unavailable(str(resolved), reason, **counts)
    return {
        "source": SOURCE_LABEL,
        "path": str(resolved),
        "available": True,
        "reason": "",
        "receipts": list(found.receipts.values()),
        **counts,
    }
