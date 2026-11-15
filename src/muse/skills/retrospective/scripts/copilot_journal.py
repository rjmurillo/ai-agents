"""Bounded execution receipts from an explicit native Copilot CLI journal.

``extract_evidence.py`` calls this module when a retrospective has no toolkit
session log but the user names a Copilot ``events.jsonl`` journal. The journal
is the execution source. Git history stays corroboration.

Reuse: record reading, event de-duplication, subagent filtering and the
repository-scope test come from the sibling ``skill-doctor`` scripts. This
module does not call ``parse_copilot_session``, because that parser keeps
prompt, assistant and tool-result text. A receipt is an allowlist of fields:
tool name, call id, outcome, a short error code, the argument shape, and a
timestamp. No prompt, instruction, reasoning, argument value or result content
is read into the output.

Safety contract:
  * Only the path the caller passes is read. Nothing is discovered or globbed.
  * Every working directory the journal records must sit inside the selected
    repository. A journal with no recorded working directory fails closed.
  * An unreadable, out-of-scope or receipt-free journal is reported as
    unavailable with a reason, never as success.
  * Reads and output are capped, and the report states caps and skipped records.
  * Nothing is written. No toolkit session log is created (issue #5228).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

SOURCE_LABEL = "copilot-cli native journal (explicit path)"
MAX_RECEIPTS = 200
MAX_RECORDS = 100_000
_MAX_FIELD_CHARS = 120
_CONTEXT_EVENTS = ("session.start", "session.context_changed")


def _doctor_scripts_dir() -> Path:
    """Return the sibling skill-doctor scripts directory in this plugin root."""
    return Path(__file__).resolve().parents[2] / "skill-doctor" / "scripts"


def _load_doctor() -> tuple[Any, Any, Any] | None:
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
        import session_common
        import session_discovery
        import session_json
    except ImportError:
        return None
    return session_common, session_discovery, session_json


def _clean(value: object) -> str | None:
    """Return a printable, length-bounded string for a str or int, else None."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = "".join(ch for ch in str(value) if ch.isprintable())
    return text[:_MAX_FIELD_CHARS] or None


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


def _start_receipt(obj: dict[str, Any]) -> dict[str, Any] | None:
    data = obj["data"]
    call_id = _clean(data.get("toolCallId"))
    if call_id is None:
        return None
    return {
        "tool": _clean(data.get("toolName")) or "unknown",
        "call_id": call_id,
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


def _recorded_cwds(data: dict[str, Any]) -> Iterator[str]:
    context = data.get("context", data)
    if isinstance(context, dict):
        for key in ("cwd", "gitRoot"):
            if isinstance(context.get(key), str) and context[key]:
                yield context[key]


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
            self.cwds.extend(_recorded_cwds(data))
        elif kind == "tool.execution_start":
            self._start(obj)
        elif kind == "tool.execution_complete":
            receipt = self.receipts.get(_clean(data.get("toolCallId")) or "")
            if receipt is None:
                self.unmatched += 1
            else:
                _complete_receipt(receipt, data)

    def _start(self, obj: dict[str, Any]) -> None:
        self.starts += 1
        receipt = _start_receipt(obj)
        if receipt is None:
            self.no_call_id += 1
        elif len(self.receipts) < MAX_RECEIPTS:
            self.receipts.setdefault(receipt["call_id"], receipt)
        elif receipt["call_id"] not in self.receipts:
            self.capped = True


def extract_receipts(journal: Path, project_dir: Path) -> dict[str, Any]:
    """Return a bounded receipt report for ``journal`` within ``project_dir``.

    The report always carries ``available`` and, when False, a ``reason``.
    """
    label = str(journal)
    doctor = _load_doctor()
    if doctor is None:
        return _unavailable(label, "skill-doctor parser unavailable in this plugin root")
    common, discovery, parser = doctor
    try:
        resolved = journal.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        return _unavailable(label, f"journal not readable: {type(exc).__name__}")
    if not resolved.is_file():
        return _unavailable(str(resolved), "journal path is not a regular file")

    repo = project_dir.resolve()
    stats = {"read": 0, "truncated": False}
    found = _Collector()

    with common.collect_diagnostics():
        try:
            records = common.iter_jsonl_records(resolved)
        except OSError as exc:
            return _unavailable(str(resolved), f"journal not readable: {type(exc).__name__}")

        def counted() -> Iterator[dict[str, Any]]:
            for record in records:
                if stats["read"] >= MAX_RECORDS:
                    stats["truncated"] = True
                    return
                stats["read"] += 1
                yield record

        for obj in parser._copilot_events(counted(), False):
            found.feed(obj)
        records.close()
        issues = common.collection_issue_counts()

    counts = {
        "records_read": stats["read"],
        "records_cap": MAX_RECORDS,
        "records_truncated": stats["truncated"],
        "malformed_lines": issues.get("malformed_records", 0),
        "records_filtered": stats["read"] - found.used,
        "tool_starts": found.starts,
        "starts_without_call_id": found.no_call_id,
        "completions_without_retained_start": found.unmatched,
        "receipts_cap": MAX_RECEIPTS,
        "receipts_truncated": found.capped,
    }
    path = str(resolved)
    if not found.cwds:
        return _unavailable(
            path, "journal records no working directory; scope not confirmed", **counts
        )
    if not all(discovery.session_cwd_within_repo(cwd, repo) for cwd in found.cwds):
        return _unavailable(
            path, "journal records a working directory outside the repository", **counts
        )
    if not found.receipts:
        return _unavailable(path, "journal holds no tool execution records", **counts)
    return {
        "source": SOURCE_LABEL,
        "path": path,
        "available": True,
        "reason": "",
        "receipts": list(found.receipts.values()),
        **counts,
    }
