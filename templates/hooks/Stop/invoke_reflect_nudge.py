#!/usr/bin/env python3
"""Nudge the operator to run ``reflect`` when a session holds unrecorded corrections.

Deterministic scan, no model call and no network. The Stop payload carries
``session_id``, ``transcript_path`` and ``cwd`` (not ``messages``, the field the
deleted hook read, issue #3184). The scanner reads the transcript JSONL the
harness already wrote, counts correction and praise signals in human turns, and
asks ``reflect`` to review them. The hook never writes memory: ``reflect``
requires the operator to approve each learning.

Hook Type: Stop (blocks at most once per session per signal set, fail-open)
Exit Codes:
    0 = always. A block is a stdout JSON decision, never a non-zero exit code,
        so a hook fault cannot wedge the end of a turn.

Disable: set ``REFLECT_NUDGE_DISABLE=1`` (for example under ``env`` in
``settings.local.json``).

Human turns are selected on positive evidence: ``origin.kind == "human"``, no
``toolUseResult``, not a sidechain, not ``isMeta``, and not a harness wrapper
such as ``<command-name>``. Tool results are recorded as ``user`` records, so a
scanner that trusts ``type == "user"`` reads file contents as operator speech.

References:
    - Issue #5817 (this hook), #5820 (PRD), #3184 (dead Stop hook), #1761
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HOOK_NAME = "reflect-trigger"
DISABLE_ENV = "REFLECT_NUDGE_DISABLE"
MARKER_MAX_AGE_SECONDS = 30 * 24 * 3600
TURN_SCAN_CHARS = 200
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_CORRECTION = re.compile(
    r"^(?:"
    r"(?:no|nope|wrong|incorrect)(?:[\s,.!:;-]|$)"
    r"(?!\s*(?:problem|worries|need|thanks|rush|hurry|go ahead|proceed|that'?s fine|looks good))"
    r"|(?:that'?s|that is|this is|it'?s) (?:wrong|incorrect|not (?:right|correct|what))"
    r"|not (?:like that|quite)"
    r"|i meant\b"
    r"|don'?t ever\b|do not ever\b|never (?:do|use|add|run|say)\b"
    r"|stop (?:doing|using|adding|running)\b"
    r")"
)
_WRAPPER = re.compile(r"^<[a-z]+(?:-[a-z]+)+[ >]")
_PRAISE = re.compile(
    r"^(?:perfect|exactly|that'?s it|that'?s exactly|great|excellent)(?:[\s,.!:;-]|$)"
)


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    root = Path(base) if base else Path.home() / ".local" / "state"
    return root / "ai-agents" / "reflect-nudge"


def _turn_text(record: dict[str, Any]) -> str | None:
    """Return the text of a human turn, or None when the record is not one."""
    if record.get("type") != "user" or "toolUseResult" in record:
        return None
    if record.get("isSidechain") or record.get("isMeta"):
        return None
    origin = record.get("origin")
    if not isinstance(origin, dict) or origin.get("kind") != "human":
        return None
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = " ".join(
            b["text"]
            for b in content
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        )
    if not isinstance(content, str):
        return None
    text = content.strip()
    return None if not text or _WRAPPER.match(text) else text


def scan_transcript(path: Path) -> dict[str, int]:
    """Count records and signals. Malformed lines are skipped and counted."""
    counts = {"user_records": 0, "human_turns": 0, "high": 0, "med": 0, "skipped": 0}
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                counts["skipped"] += 1
                continue
            if not isinstance(record, dict):
                counts["skipped"] += 1
                continue
            _tally(record, counts)
    return counts


def _tally(record: dict[str, Any], counts: dict[str, int]) -> None:
    if record.get("type") == "user":
        counts["user_records"] += 1
    text = _turn_text(record)
    if text is None:
        return
    counts["human_turns"] += 1
    head = text[:TURN_SCAN_CHARS].lower()
    if _CORRECTION.match(head):
        counts["high"] += 1
    elif _PRAISE.match(head):
        counts["med"] += 1


def qualifies(counts: dict[str, int]) -> bool:
    """Same threshold as the reflect skill: >=1 HIGH or >=2 MED."""
    return counts["high"] >= 1 or counts["med"] >= 2


def signal_hash(counts: dict[str, int]) -> str:
    return hashlib.sha256(f"{counts['high']}:{counts['med']}".encode()).hexdigest()[:16]


def _marker_path(session_id: str) -> Path | None:
    directory = _state_dir()
    for component in (directory, directory.parent, directory.parent.parent):
        if component.is_symlink():
            return None
    return directory / f"{session_id}.json"


def _read_marker(marker: Path) -> dict[str, Any]:
    """Read a marker without following a symlink planted at the file itself."""
    fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        return dict(json.load(handle))


def already_nudged(session_id: str, digest: str) -> bool:
    """True when the marker records this signal set. A torn marker reads as nudged."""
    marker = _marker_path(session_id)
    if marker is None:
        return True
    try:
        return bool(_read_marker(marker).get("signal") == digest)
    except FileNotFoundError:
        return False
    except (OSError, ValueError, TypeError):
        return True


def write_marker(session_id: str, digest: str) -> bool:
    """Atomically write an owner-only marker outside the repository."""
    marker = _marker_path(session_id)
    if marker is None:
        return False
    try:
        marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=marker.parent, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump({"signal": digest}, tmp)
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, marker)
    except OSError:
        return False
    _prune(marker.parent)
    return True


def _prune(directory: Path) -> None:
    cutoff = time.time() - MARKER_MAX_AGE_SECONDS
    try:
        for entry in directory.glob("*.json"):
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
    except OSError:
        return


def _log(message: str) -> None:
    print(f"{HOOK_NAME}: {message}", file=sys.stderr)


def _transcript(payload: dict[str, Any]) -> Path | None:
    raw = payload.get("transcript_path")
    if not isinstance(raw, str) or not raw:
        _log("no transcript_path in payload (fail-open, no block)")
        return None
    path = Path(raw).resolve()
    if not path.is_file():
        _log(f"transcript unreadable at {path} (fail-open, no block)")
        return None
    return path


def _session_id(payload: dict[str, Any]) -> str | None:
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and SESSION_ID_PATTERN.match(session_id):
        return session_id
    _log("missing or invalid session_id (fail-open, no block)")
    return None


def _decision(counts: dict[str, int]) -> str:
    reason = (
        f"This session has {counts['high']} correction and {counts['med']} praise signals "
        "not yet recorded. Run the reflect skill to review them and approve which learnings "
        "to keep."
    )
    return json.dumps({"decision": "block", "reason": reason})


def _read_payload() -> dict[str, Any]:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    """Scan the transcript and emit one block decision when warranted."""
    if os.environ.get(DISABLE_ENV, "").strip() not in ("", "0"):
        return 0
    payload = _read_payload()
    if payload.get("stop_hook_active"):
        return 0
    path = _transcript(payload)
    session_id = _session_id(payload)
    if path is None or session_id is None:
        return 0
    counts = scan_transcript(path)
    state = "silent"
    digest = signal_hash(counts)
    if (
        qualifies(counts)
        and not already_nudged(session_id, digest)
        and write_marker(session_id, digest)
    ):
        print(_decision(counts))
        state = "nudged"
    if counts["user_records"] and not counts["human_turns"]:
        _log("user records present but none carry origin.kind human (schema drift?)")
    _log(
        f"{counts['user_records']} user records, {counts['human_turns']} human turns, "
        f"{counts['high']} HIGH, {counts['med']} MED, {counts['skipped']} skipped ({state})"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail-open: a hook fault must not wedge the turn
        print(f"[WARNING] {HOOK_NAME} error: {exc}", file=sys.stderr)
        sys.exit(0)
