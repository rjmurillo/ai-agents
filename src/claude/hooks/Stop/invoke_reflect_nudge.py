#!/usr/bin/env python3
"""Nudge the operator to run the reflect skill when a session holds corrections.

Detection is a deterministic scan of the transcript file the harness already
wrote. No model call, no network, no SDK. Extraction stays inside the reflect
skill, behind the approval it already requires. This hook proposes and stops:
it never invokes reflect and never writes memory.

Hook Type: Stop (non-blocking, fail-open)
Exit Codes:
    0 = always. The hook never emits ``decision: "block"`` and never exits 2,
        so it cannot trap a session or loop on re-entry. A nudge is a
        ``systemMessage`` advisory on stdout. Every internal error exits 0.
        The registered command ends in ``|| true`` because python itself
        exits 2 when the script file is missing, and exit 2 on Stop blocks.

Stop payload (source: issue #3184, which probed the real event; the
agent-harness-reference skill does not define these fields): "the Claude Code
Stop payload carries `session_id`, `transcript_path`, and `cwd`, not
`messages`."
    {"session_id": "...", "transcript_path": "...", "cwd": "..."}
The deleted invoke_skill_learning.py read ``hook_input["messages"]``, a field
the event never sent, and early-returned on every Stop. This hook reads
``transcript_path`` and reports the fail-open reason when it is absent.

Transcript contract (measured on real sessions, issue #5817): newline-delimited
JSON. ``type == "user"`` also covers tool results, which carry
``toolUseResult``. A human turn is selected positively: ``origin.kind ==
"human"`` (or, on records with no ``origin``, ``promptSource`` of ``typed`` or
``queued``), no ``toolUseResult``, not ``isMeta``, not ``isSidechain``.

Dedupe marker: one file per (session, signal set) under per-user state
outside any repository, mode 0o600 in an owner-only 0o700 directory. It is
claimed with an exclusive create (O_CREAT | O_EXCL), so overlapping Stop
events cannot both nudge: the loser sees the file exists and stays silent.
The name carries a hash of the counts. The body holds counts, never
transcript text.

Calibration status (issue #5820, AC-9): the patterns are anchored at the
start of a turn or are fixed phrases, and were tuned on one operator's
191 human turns. Recall was not measured. See the pull request that
introduced this hook for the examined counts and the limits.

References:
    - Issue #5817 (this hook), #5820 (PRD), #3184 (the no-op it replaces)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

HOOK_NAME = "reflect-trigger"
MARKER_VERSION = 1
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")
STATE_SUBDIR = "ai-agents-reflect-nudge"

MAX_STDIN_BYTES = 1_000_000
MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
MAX_LINE_CHARS = 1024 * 1024
SCAN_BUDGET_SECONDS = 2.0
MAX_TURN_CHARS = 1000
MARKER_MAX_AGE_SECONDS = 30 * 24 * 3600
MARKER_PRUNE_LIMIT = 500
OVERLONG_LINE = "\x00"  # not valid JSON, so the caller counts it as skipped
HUMAN_PROMPT_SOURCES = frozenset({"typed", "queued"})
MED_THRESHOLD = 2

# HIGH: corrections. Anchored openers or fixed phrases, never a bare "no".
HIGH_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\s*(?:no|nope)\s*(?:[,.!:;]|$)",
        r"^\s*(?:wrong|incorrect)\b",
        r"\bnot like that\b",
        r"^\s*not quite\b",
        r"^\s*(?:ok[,.]?\s+)?try again\b",
        r"\bthat(?:'|’)?s (?:wrong|incorrect|not (?:right|correct|what i))\b",
        r"\bthat is (?:wrong|incorrect|not (?:right|correct))\b",
        r"^\s*i meant\b",
        r"\b(?:never|always) do\b",
        r"\bdon(?:'|’)?t ever\b",
        r"\bstop (?:doing|using|adding)\b",
    )
)
# MED: praise. Anchored openers only.
MED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\s*(?:perfect|exactly|great|nice)\b",
        r"^\s*(?:yes[,.!]?\s+)?that(?:'|’)?s (?:it|exactly)\b",
    )
)


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Counts from one transcript scan. Never holds transcript text."""

    user_records: int = 0
    human_turns: int = 0
    high: int = 0
    med: int = 0
    skipped_lines: int = 0
    truncated: bool = False


def read_payload(stream: IO[str]) -> dict[str, Any] | None:
    """Return the Stop payload object, or None when absent or malformed."""
    try:
        raw = stream.read(MAX_STDIN_BYTES + 1)
        if len(raw.encode("utf-8", errors="replace")) > MAX_STDIN_BYTES:
            return None
        payload = json.loads(raw)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def is_human_turn(record: Mapping[str, Any]) -> bool:
    """Select a human-typed turn on positive evidence only."""
    if record.get("type") != "user":
        return False
    if "toolUseResult" in record or record.get("isMeta") or record.get("isSidechain"):
        return False
    origin = record.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    return origin is None and record.get("promptSource") in HUMAN_PROMPT_SOURCES


def human_text(record: Mapping[str, Any]) -> str:
    """Return the leading text of a human turn, bounded to MAX_TURN_CHARS."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict)]
        content = " ".join(p for p in parts if isinstance(p, str) and p)
    if not isinstance(content, str):
        return ""
    text = content.lstrip()
    # A leading "<" marks harness wrappers (command echoes, notifications).
    return "" if text.startswith("<") else text[:MAX_TURN_CHARS]


def classify(text: str) -> tuple[bool, bool]:
    """Return (is_correction, is_praise) for one human turn."""
    return (
        any(p.search(text) for p in HIGH_PATTERNS),
        any(p.search(text) for p in MED_PATTERNS),
    )


def open_transcript(raw_path: str) -> IO[str] | None:
    """Open a regular, size-capped transcript, or return None.

    Opens first and checks the open descriptor, so a path swapped for a FIFO
    between a check and the open cannot block the hook. O_NONBLOCK keeps a
    swapped-in FIFO from blocking the open itself.
    """
    path = Path(raw_path).resolve()
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_TRANSCRIPT_BYTES:
        os.close(fd)
        return None
    return os.fdopen(fd, "r", encoding="utf-8", errors="replace")


def _bounded_lines(handle: IO[str]) -> Iterator[str]:
    """Yield lines, replacing any line over MAX_LINE_CHARS with OVERLONG_LINE.

    The remainder of an over-long line is consumed in bounded chunks, so one
    huge record cannot exhaust time or memory. The caller counts the
    placeholder as a skipped line.
    """
    while True:
        chunk = handle.readline(MAX_LINE_CHARS)
        if not chunk:
            return
        if chunk.endswith("\n") or len(chunk) < MAX_LINE_CHARS:
            yield chunk
            continue
        while chunk and not chunk.endswith("\n"):
            chunk = handle.readline(MAX_LINE_CHARS)
        yield OVERLONG_LINE


def scan_transcript(
    handle: IO[str],
    *,
    clock: Callable[[], float] = time.monotonic,
    budget: float = SCAN_BUDGET_SECONDS,
) -> ScanResult:
    """Stream the transcript once, stopping at the wall-clock budget."""
    deadline = clock() + budget
    counts = {"user": 0, "human": 0, "high": 0, "med": 0, "skipped": 0}
    truncated = False
    for line in _bounded_lines(handle):
        if clock() > deadline:
            truncated = True
            break
        _scan_line(line, counts)
    return ScanResult(
        user_records=counts["user"],
        human_turns=counts["human"],
        high=counts["high"],
        med=counts["med"],
        skipped_lines=counts["skipped"],
        truncated=truncated,
    )


def _scan_line(line: str, counts: dict[str, int]) -> None:
    if not line.strip():
        return
    try:
        record = json.loads(line)
    except (ValueError, RecursionError):
        counts["skipped"] += 1
        return
    if not isinstance(record, dict):
        counts["skipped"] += 1
        return
    if record.get("type") == "user":
        counts["user"] += 1
    if not is_human_turn(record):
        return
    counts["human"] += 1
    correction, praise = classify(human_text(record))
    counts["high"] += int(correction)
    counts["med"] += int(praise and not correction)


def has_signal(result: ScanResult) -> bool:
    """Apply the reflect thresholds: at least 1 HIGH or 2 MED."""
    return result.high >= 1 or result.med >= MED_THRESHOLD


def signal_hash(result: ScanResult) -> str:
    """Hash of the signal set, so a changed set earns a new nudge."""
    return hashlib.sha256(f"{result.high}:{result.med}".encode()).hexdigest()[:16]


def default_state_root(env: Mapping[str, str], os_name: str = os.name) -> Path:
    """Per-user state directory root, outside any repository."""
    if os_name == "nt":
        base = env.get("LOCALAPPDATA")
        return Path(base) if base else Path.home() / "AppData" / "Local"
    xdg = env.get("XDG_STATE_HOME")
    if xdg and Path(xdg).is_absolute():
        return Path(xdg)
    return Path.home() / ".local" / "state"


def _safe_marker_dir(state_root: Path) -> Path | None:
    """Create or validate the 0o700 marker directory, refusing symlinks.

    The state root is resolved first, so a symlinked state root (a dotfile
    manager, for example) works and every later check runs on the real path.
    The root is not mode-checked: a 0o002 umask makes group-writable roots
    normal. A directory another user pre-creates under it fails the owner and
    0o700 checks below, which is what protects the marker.
    """
    state_root.mkdir(parents=True, exist_ok=True)
    root = state_root.resolve()
    if not _owned_by_current_user(root.lstat()):
        return None
    target = root / STATE_SUBDIR
    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = target.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return None
    return target if _owned_by_current_user(info) and _is_private(info) else None


def _owned_by_current_user(info: os.stat_result) -> bool:
    return not hasattr(os, "getuid") or info.st_uid == os.getuid()


def _is_private(info: os.stat_result) -> bool:
    """True when group and other have no access (the 0o700 rule)."""
    return os.name == "nt" or (info.st_mode & 0o077) == 0


def claim_marker(directory: Path, session_id: str, result: ScanResult) -> bool:
    """Atomically claim the (session, signal set) marker.

    Returns True for the one caller that created it and False when it already
    exists. O_EXCL makes the create atomic across overlapping Stop events and
    refuses to follow a symlink planted at the leaf.
    """
    marker = directory / f"{session_id}.{signal_hash(result)}.json"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(marker, flags, 0o600)
    except FileExistsError:
        return False
    body = {"v": MARKER_VERSION, "high": result.high, "med": result.med}
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(body, handle)
    return True


def prune_markers(directory: Path, now: float) -> None:
    """Remove markers older than MARKER_MAX_AGE_SECONDS, bounded per run."""
    for index, entry in enumerate(directory.iterdir()):
        if index >= MARKER_PRUNE_LIMIT:
            return
        try:
            if now - entry.lstat().st_mtime > MARKER_MAX_AGE_SECONDS:
                entry.unlink()
        except OSError:
            continue


def build_message(result: ScanResult) -> str:
    """Counts and the skill name only. Never quotes transcript text."""
    return (
        f"{HOOK_NAME}: detected {result.high} correction and "
        f"{result.med} praise signal(s) in this session. "
        "Run the reflect skill to review and approve what to keep."
    )


def status_line(result: ScanResult, outcome: str) -> str:
    """Examined counts beside findings (ci-scripts MUST-12)."""
    tail = ", scan truncated at budget" if result.truncated else ""
    return (
        f"{HOOK_NAME}: {result.user_records} user records, "
        f"{result.human_turns} human turns, {result.high} HIGH, "
        f"{result.med} MED, {result.skipped_lines} skipped lines "
        f"({outcome}{tail})"
    )


def _fail_open(stderr: IO[str], reason: str) -> int:
    print(f"{HOOK_NAME}: {reason} (fail-open, no nudge)", file=stderr)
    return 0


def run(
    stdin: IO[str],
    stdout: IO[str],
    stderr: IO[str],
    env: Mapping[str, str],
    *,
    state_root: Path | None = None,
    clock: Callable[[], float] = time.monotonic,
    now: Callable[[], float] = time.time,
) -> int:
    """Run one Stop event. Always returns 0."""
    payload = read_payload(stdin)
    if payload is None:
        return _fail_open(stderr, "stop payload missing or malformed")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
        return _fail_open(stderr, "session_id missing or invalid")
    raw_path = payload.get("transcript_path")
    handle = open_transcript(raw_path) if isinstance(raw_path, str) and raw_path.strip() else None
    if handle is None:
        return _fail_open(stderr, "transcript_path missing, unreadable, or too large")
    with handle:
        result = scan_transcript(handle, clock=clock)
    if not has_signal(result):
        print(status_line(result, "silent"), file=stderr)
        return 0
    root = state_root or default_state_root(env)
    return _nudge_once(result, session_id, stdout, stderr, root, now)


def _nudge_once(
    result: ScanResult,
    session_id: str,
    stdout: IO[str],
    stderr: IO[str],
    state_root: Path,
    now: Callable[[], float],
) -> int:
    directory = _safe_marker_dir(state_root)
    if directory is None:
        return _fail_open(stderr, "marker directory unsafe")
    if not claim_marker(directory, session_id, result):
        print(status_line(result, "already nudged"), file=stderr)
        return 0
    print(json.dumps({"systemMessage": build_message(result)}), file=stdout, flush=True)
    print(status_line(result, "nudged"), file=stderr)
    try:
        prune_markers(directory, now())
    except OSError:
        print(f"{HOOK_NAME}: marker prune failed (ignored)", file=stderr)
    return 0


def main() -> int:
    """Entry point. Any internal error exits 0."""
    try:
        return run(sys.stdin, sys.stdout, sys.stderr, os.environ)
    except Exception as exc:  # fail-open: a crashing Stop hook must not trap the session
        print(f"[WARNING] {HOOK_NAME} error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
