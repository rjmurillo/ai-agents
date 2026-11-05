#!/usr/bin/env python3
"""Nudge the operator to run the reflect skill when a session holds corrections.

Detection is a deterministic scan of the transcript file the harness already
wrote. No model call, no network, no SDK. Extraction stays inside the reflect
skill, behind the approval it already requires. This hook proposes and stops:
it never invokes reflect and never writes memory.

Hook Type: Stop (non-blocking, fail-open)
Exit Codes:
    0 = always. The hook never emits ``decision: "block"`` and never exits 2,
        so it cannot trap a session or loop. A nudge is a ``systemMessage``
        advisory on stdout. Every internal error exits 0. Python exits 2 on
        a missing script, and exit 2 on Stop blocks, so the registered
        command checks the dispatcher file first and exits 0 when it is
        missing. The advisory launcher then exits 0 on every failure path.

Stop payload (issue #3184 probed the real event): ``session_id``, ``transcript_path``,
and ``cwd``, not ``messages``. A missing ``transcript_path`` is the fail-open reason.

Transcript contract (measured on real sessions, issue #5817): newline-delimited
JSON. ``type == "user"`` also covers tool results, which carry
``toolUseResult``. A human turn is selected positively: ``origin.kind ==
"human"`` (or, on records with no ``origin``, ``promptSource`` of ``typed`` or
``queued``), no ``toolUseResult``, not ``isMeta``, not ``isSidechain``.

Dedupe marker: one file per (session, signal set) under per-user state
outside any repository (mode 0o600, in a 0o700 directory), claimed with an
exclusive create (O_CREAT | O_EXCL) so overlapping Stops cannot both nudge.
The name hashes the counts; the body holds counts, never transcript text.

Friction branch (REQ-048 TASK-003): the scan keeps conversation records, up
to MAX_FRICTION_RECORDS, and the shared ``failure_classifier`` (``lib/``)
scores them, one marker per (session, tier). Firing bound: at most one
friction nudge per session per threshold tier. Off is read before any I/O.
A budget stop, a missing lib, or a lib error skips friction only; stderr says so.
Customer value: retro prompt after repeated failures. Off: AI_AGENTS_RETRO_NUDGE_THRESHOLD=0|off.

Calibration status (issue #5820, AC-9): patterns are turn-anchored or fixed
phrases, except one bounded "use ... instead" window, tuned on one operator's
191 human turns. Recall was not measured.

HIGH patterns under "Adapted from claude-mem" adapt thedotmack/claude-mem
(Apache-2.0) acr/patterns.py and behavior.py at commit 356b7c08f64c, fixed
phrases only. Bare words ("already", "stop", "never", "again") and profanity
other than "wtf" were dropped as too broad.

The newer patterns ("we don't use/open" HIGH; MED "use ... instead",
"prefer", "I don't want", "I don't like") were read by hand on 326 human
turns of 30-day Claude Code history: every match was a real correction or
preference. Codex and Droid history (141 and 97 turns) found no new false
positive except "rather than" (pasted prose in 4 of 5), left out. Recall
was not measured.

References: issue #5817 (this hook), #5820 (PRD), #3184 (the replaced no-op).
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import stat
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from failure_classifier import Friction

# Hooks run from repo and plugin trees: write no __pycache__ beside them.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling state module
from _reflect_nudge_state import (  # noqa: E402
    claim,
    is_off,
    prune_markers,
    resolve_state_root,
    safe_marker_dir,
)

HOOK_NAME = "reflect-trigger"
MARKER_VERSION = 1
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")

MAX_STDIN_BYTES = 1_000_000
MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
MAX_LINE_CHARS = 1024 * 1024
MAX_FRICTION_RECORDS = 200_000
SCAN_BUDGET_SECONDS = 2.0
MAX_TURN_CHARS = 1000
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
        # Adapted from claude-mem acr/patterns.py and acr/behavior.py.
        r"\b(?:i told you|like i said)\b",
        r"\bhow many times (?:do|did|have|must|should) i\b",
        r"\bstop asking\b",
        r"\bi did(?:n(?:'|’)?t| not) (?:ask|say|tell you)\b",
        r"\bnot what i (?:asked|wanted|meant)\b",
        r"\b(?:no ?one|nobody) (?:said|asked)\b",
        r"\bmade (?:that|it) up\b",
        r"\bdid you (?:actually|even) (?:run|test|check|read|try|look|verify)\b",
        r"\bwrong (?:repo|branch|file)\b",
        r"\byou broke (?:the|this|that|my|it)\b(?!\s+down)",
        r"\bwtf\b",
        r"\bthat(?:'|’)?s (?:dumb|stupid)\b",
        # Observed in operator transcripts: correcting a stated assumption.
        r"\bwe (?:don(?:'|’)?t|do not|never) (?:use|open)\b",
    )
)
# MED: praise (anchored openers) and stated preferences (fixed phrases and
# one bounded "use ... instead" window).
MED_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\s*(?:perfect|exactly|great|nice)\b",
        r"^\s*(?:yes[,.!]?\s+)?that(?:'|’)?s (?:it|exactly)\b",
        r"\bi (?:also |really |just )?(?:don(?:'|’)?t|do not) (?:want|like)\b",
        r"\buse\b[^.?!\n]{1,60}\binstead\b",
        r"\bi(?: would|(?:'|’)d)? prefer\b",
        r"(?:^|[;:.!]\s*)prefer\b",
    )
)


def _load_classifier() -> ModuleType | None:
    """Import the shared classifier from ``<root>/lib``, or None when absent.

    The path comes from this file's own location, never an env var (AC-22).
    """
    lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
    if os.path.isdir(lib_dir) and lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    try:
        return importlib.import_module("failure_classifier")
    except Exception:  # fail-open: a broken lib must not break the correction branch
        return None


failure_classifier: Any = _load_classifier()


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Counts from one transcript scan. Never holds transcript text.

    ``records`` (friction input) stays out of equality and repr.
    ``stopped_on`` is ``time`` or ``bytes``; ``dropped_records`` counts
    records past the event cap.
    """

    user_records: int = 0
    human_turns: int = 0
    high: int = 0
    med: int = 0
    skipped_lines: int = 0
    truncated: bool = False
    stopped_on: str = ""
    dropped_records: int = 0
    lines_scanned: int = 0
    records: tuple[Mapping[str, Any], ...] = field(default=(), compare=False, repr=False)
    collect_failed: bool = field(default=False, compare=False, repr=False)


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
    """Return (is_correction, is_praise_or_preference) for one human turn."""
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
    collect: bool = False,
) -> ScanResult:
    """Stream the transcript once, stopping at the time or byte budget.

    With ``collect`` the decoded conversation records are kept, up to
    MAX_FRICTION_RECORDS, for the friction branch.
    """
    deadline = clock() + budget
    counts = dict.fromkeys(
        ("user", "human", "high", "med", "skipped", "dropped", "lines", "collect_failed"), 0
    )
    kept: list[Mapping[str, Any]] | None = [] if collect and failure_classifier else None
    stopped_on = ""
    seen_bytes = 0
    for line in _bounded_lines(handle):
        if clock() > deadline:
            stopped_on = "time"
            break
        # Count each U+FFFD (errors="replace") as one byte: never above real size.
        seen_bytes += len(line.encode("utf-8")) - 2 * line.count("\ufffd")
        if seen_bytes > MAX_TRANSCRIPT_BYTES:
            stopped_on = "bytes"
            break
        counts["lines"] += 1
        _scan_line(line, counts, kept)
    return ScanResult(
        user_records=counts["user"],
        human_turns=counts["human"],
        high=counts["high"],
        med=counts["med"],
        skipped_lines=counts["skipped"],
        truncated=bool(stopped_on),
        stopped_on=stopped_on,
        dropped_records=counts["dropped"],
        lines_scanned=counts["lines"],
        records=tuple(kept) if kept is not None else (),
        collect_failed=bool(counts["collect_failed"]),
    )


def _scan_line(
    line: str, counts: dict[str, int], kept: list[Mapping[str, Any]] | None = None
) -> None:
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
    if kept is not None and not counts["collect_failed"]:
        try:
            counts["dropped"] += failure_classifier.collect_record(
                kept, record, MAX_FRICTION_RECORDS
            )
        except Exception:  # fail-open: a broken lib skips friction only
            counts["collect_failed"] = 1
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


def claim_marker(directory: Path, session_id: str, result: ScanResult) -> bool:
    """Atomically claim the (session, signal set) correction marker."""
    body = {"v": MARKER_VERSION, "high": result.high, "med": result.med}
    return claim(directory, f"{session_id}.{signal_hash(result)}.json", body)


def claim_friction_marker(directory: Path, session_id: str, friction: Friction) -> bool:
    """Atomically claim the (session, tier) friction marker. Body: counts only."""
    fc = failure_classifier
    name = fc.friction_marker_name(session_id, friction.tier, MARKER_VERSION)
    return claim(directory, name, fc.friction_marker_body(friction, MARKER_VERSION))


def build_message(result: ScanResult) -> str:
    """Counts and the skill name only. Never quotes transcript text."""
    return (
        f"{HOOK_NAME}: this session holds {result.high} correction and "
        f"{result.med} praise or preference signal(s). "
        "You can run /reflect to review and approve what to keep."
    )


def status_line(result: ScanResult, outcome: str, note: str = "") -> str:
    """Examined counts beside findings (ci-scripts MUST-12)."""
    cut = f", scan truncated at {result.stopped_on} budget" if result.stopped_on else ""
    return (
        f"{HOOK_NAME}: {result.lines_scanned} lines scanned, {result.user_records} user records, "
        f"{result.human_turns} human turns, {result.high} HIGH, "
        f"{result.med} MED, {result.skipped_lines} skipped lines, "
        f"{result.dropped_records} records over event cap ({outcome}{cut}{note})"
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
    if is_off(env):
        return 0  # AC-12, AC-20: off is checked before any read or write
    fc = failure_classifier
    threshold: int | None = None
    if fc is not None:
        try:
            threshold = fc.parse_threshold(env)
        except Exception:  # fail-open: a broken lib skips friction only
            fc = None
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
        result = scan_transcript(handle, clock=clock, collect=fc is not None)
    friction, note = _friction(fc, result, threshold)
    wants_friction = friction is not None and friction.tier >= 1
    if not (has_signal(result) or wants_friction):
        print(status_line(result, "silent", note), file=stderr)
        return 0
    root, refusal = resolve_state_root(env, state_root)
    if root is None:  # AC-24: no mkdir, no systemMessage, one stderr line
        return _fail_open(stderr, refusal)
    return _nudge_once(result, friction, session_id, (stdout, stderr), root, now, note)


def _friction(
    fc: ModuleType | None, result: ScanResult, threshold: int | None
) -> tuple[Friction | None, str]:
    """Score friction; any classifier error skips friction and keeps correction."""
    if fc is None or threshold is None or result.collect_failed:
        return None, ", friction skipped: classifier unavailable"
    try:
        if fc.partial_budget(result.stopped_on, result.dropped_records):
            return None, fc.friction_status(result.stopped_on, result.dropped_records, None)
        friction = fc.compute_friction(result.records, threshold)
        return friction, fc.friction_status(result.stopped_on, result.dropped_records, friction)
    except Exception:  # fail-open: a broken lib skips friction only
        return None, ", friction skipped: classifier error"


def _nudge_once(
    result: ScanResult,
    friction: Friction | None,
    session_id: str,
    streams: tuple[IO[str], IO[str]],
    state_root: Path,
    now: Callable[[], float],
    note: str,
) -> int:
    stdout, stderr = streams
    directory = safe_marker_dir(state_root)
    if directory is None:
        return _fail_open(stderr, "marker directory unsafe")
    messages: list[str] = []
    if has_signal(result) and claim_marker(directory, session_id, result):
        messages.append(build_message(result))
    if friction is not None and friction.tier >= 1:
        try:  # fail-open: a broken lib skips friction only, never the correction
            text = failure_classifier.build_friction_message(friction, HOOK_NAME)
            claimed = claim_friction_marker(directory, session_id, friction)
        except Exception:
            text, claimed, note = "", False, ", friction skipped: classifier error"
        if text and claimed:
            messages.append(text)
    if not messages:
        print(status_line(result, "already nudged", note), file=stderr)
        return 0
    print(json.dumps({"systemMessage": "\n".join(messages)}), file=stdout, flush=True)
    print(status_line(result, "nudged", note), file=stderr)
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
