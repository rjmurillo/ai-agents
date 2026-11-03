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

Friction branch (REQ-048 TASK-003): the same scan also keeps the decoded
conversation records, bounded by MAX_FRICTION_RECORDS. After the scan the
shared ``failure_classifier`` (``lib/failure_classifier``, one definition for
every consumer) turns them into a FrictionScore. Tier n needs a score of
``threshold * 2**(n-1)``. Each (session, tier) gets its own friction marker,
separate from the correction marker, so a tier fires once. The tier 1
threshold is ``AI_AGENTS_RETRO_NUDGE_THRESHOLD`` (a positive integer), else
``FRICTION_TIER1_DEFAULT``. The literal ``0`` or ``off`` turns both branches
off before any state or transcript is touched. When the scan stops on the
time, byte, or event budget, the friction branch stays silent and the status
line names the budget; the correction branch keeps working.

Calibration status (issue #5820, AC-9): the patterns are anchored at the
start of a turn or are fixed phrases, except one bounded "use ... instead"
window. The original set was tuned on one operator's 191 human turns.
Recall was not measured. See the pull request that introduced this hook
for the examined counts and the limits.

The HIGH patterns under the "Adapted from claude-mem" comment adapt the
user-side correction regexes in thedotmack/claude-mem (Apache-2.0),
plugin/skills/agent-cost-report/scripts/acr/patterns.py and behavior.py,
at commit 356b7c08f64c. Only fixed phrases were kept. Bare words such as
"already", "stop", "never", and "again", and profanity other than "wtf",
were dropped as too broad. claude-mem carries no praise regexes.

The newer transcript-derived patterns (the "we don't use/open" HIGH
phrase and the MED preference phrases) were checked against a second
corpus from the same operator: 326 distinct human turns of Claude Code
history over 30 days. Every new match in that corpus was read by hand and
was a real correction or preference. The MED phrases "use ... instead"
and "prefer" follow the MEDIUM trigger table in the reflect skill's
references/triggers.md; "I don't want" and "I don't like" come from the
transcripts. A cross-check on 30 days of Codex and Droid history (141 and
97 distinct user turns) found no new false positive except "rather than",
which matched pasted prose in 4 of 5 turns and was left out. Copilot CLI
history held only automated prompts. Recall was not measured.

References:
    - Issue #5817 (this hook), #5820 (PRD), #3184 (the no-op it replaces)
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
from typing import IO, Any

HOOK_NAME = "reflect-trigger"
MARKER_VERSION = 1
THRESHOLD_ENV = "AI_AGENTS_RETRO_NUDGE_THRESHOLD"
OFF_VALUES = frozenset({"0", "off"})
_INTEGER = re.compile(r"[+-]?[0-9]{1,18}")
FRICTION_FALLBACK_TIER1 = 10
MAX_TIER = 32
SESSION_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")
STATE_SUBDIR = "ai-agents-reflect-nudge"

MAX_STDIN_BYTES = 1_000_000
MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
MAX_LINE_CHARS = 1024 * 1024
MAX_FRICTION_RECORDS = 200_000
CONVERSATION_TYPES = frozenset({"assistant", "user"})
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
    """Import the shared classifier from the sibling ``lib`` directory, or None.

    Installed layout: ``<root>/hooks/Stop/<this file>`` beside ``<root>/lib``,
    for both ``.claude/`` and the plugin. The path comes from this file's own
    location, never from an environment variable (AC-22). A missing or broken
    library returns None, and the friction branch reports it and stays silent.
    """
    lib_dir = str(Path(__file__).resolve().parents[2] / "lib")
    if os.path.isdir(lib_dir) and lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    try:
        return importlib.import_module("failure_classifier")
    except Exception:  # fail-open: a broken lib must not break the correction branch
        return None


failure_classifier = _load_classifier()


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Counts from one transcript scan. Never holds transcript text.

    ``records`` carries the decoded conversation records for the friction
    branch. It stays out of equality and repr, and the hook discards it after
    scoring. ``stopped_on`` names the budget that ended the scan early
    (``time`` or ``bytes``). ``dropped_records`` counts records past the event
    cap: the scan still counts corrections for them, but the friction score
    would be partial.
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

    @property
    def friction_budget(self) -> str:
        """Name of the budget that makes a friction score partial, or empty."""
        if self.stopped_on:
            return self.stopped_on
        return "events" if self.dropped_records else ""


@dataclass(frozen=True, slots=True)
class Friction:
    """The four counts of a FrictionScore, plus its tier. Integers only."""

    score: int
    tier: int
    denials: int
    stop_feedback: int
    streak: int


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
    counts = {"user": 0, "human": 0, "high": 0, "med": 0, "skipped": 0, "dropped": 0, "lines": 0}
    kept: list[Mapping[str, Any]] | None = [] if collect else None
    stopped_on = ""
    seen_bytes = 0
    for line in _bounded_lines(handle):
        if clock() > deadline:
            stopped_on = "time"
            break
        seen_bytes += len(line.encode("utf-8", errors="replace"))
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
    if kept is not None:
        _keep(record, counts, kept)
    if record.get("type") == "user":
        counts["user"] += 1
    if not is_human_turn(record):
        return
    counts["human"] += 1
    correction, praise = classify(human_text(record))
    counts["high"] += int(correction)
    counts["med"] += int(praise and not correction)


def _keep(record: Mapping[str, Any], counts: dict[str, int], kept: list[Mapping[str, Any]]) -> None:
    """Keep a non-sidechain conversation record, or count it as over the cap."""
    if record.get("type") not in CONVERSATION_TYPES or record.get("isSidechain") is True:
        return
    if len(kept) >= MAX_FRICTION_RECORDS:
        counts["dropped"] += 1
        return
    kept.append(record)


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
        if base and Path(base).is_absolute():
            return Path(base)
        return Path.home() / "AppData" / "Local"
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


def _claim(directory: Path, name: str, body: Mapping[str, Any]) -> bool:
    """Create ``directory/name`` exclusively; False when it already exists.

    O_EXCL makes the create atomic across overlapping Stop events and
    refuses to follow a symlink planted at the leaf.
    """
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(directory / name, flags, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(body, handle)
    return True


def claim_marker(directory: Path, session_id: str, result: ScanResult) -> bool:
    """Atomically claim the (session, signal set) correction marker."""
    body = {"v": MARKER_VERSION, "high": result.high, "med": result.med}
    return _claim(directory, f"{session_id}.{signal_hash(result)}.json", body)


def friction_marker_name(session_id: str, tier: int) -> str:
    """Marker file name keyed on (session, marker version, "friction", tier)."""
    key = f"{session_id}:{MARKER_VERSION}:friction:{tier}"
    return f"{session_id}.friction-{hashlib.sha256(key.encode()).hexdigest()[:16]}.json"


def claim_friction_marker(directory: Path, session_id: str, friction: Friction) -> bool:
    """Atomically claim the (session, tier) friction marker. Body: counts only."""
    body = {
        "v": MARKER_VERSION,
        "tier": friction.tier,
        "score": friction.score,
        "denials": friction.denials,
        "stop_feedback": friction.stop_feedback,
        "streak": friction.streak,
    }
    return _claim(directory, friction_marker_name(session_id, friction.tier), body)


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


def parse_threshold(env: Mapping[str, str], default: int) -> int | None:
    """Return the tier 1 threshold, or None when the hook is off (AC-11 to AC-13).

    Off is the literal ``0`` or ``off`` (case-insensitive, whitespace ignored).
    ``00``, ``+0``, and ``-0`` are not off, and like a negative or non-integer
    value they select ``default``. Only ASCII digits parse as an integer.
    """
    raw = env.get(THRESHOLD_ENV)
    if raw is None:
        return default
    text = raw.strip()
    if text in OFF_VALUES or text.lower() in OFF_VALUES:
        return None
    if not _INTEGER.fullmatch(text):
        return default
    value = int(text)
    return value if value > 0 else default


def friction_tier(score: int, threshold: int) -> int:
    """Highest n with ``score >= threshold * 2**(n-1)``; 0 below the threshold."""
    tier = 0
    while tier < MAX_TIER and score >= threshold << tier:
        tier += 1
    return tier


def compute_friction(result: ScanResult, threshold: int) -> Friction | None:
    """Score the collected records, or None when the classifier is unavailable.

    The weights, the score, and the denial markers all live in
    ``failure_classifier`` (AC-43). This function holds no copy of them.
    """
    fc = failure_classifier
    if fc is None:
        return None
    signals = fc.classify(fc.events_from_records(result.records))
    feedback = fc.stop_feedback_count(result.records)
    score = fc.friction_score(signals, feedback)
    return Friction(
        score=score,
        tier=friction_tier(score, threshold),
        denials=signals.permission_denial,
        stop_feedback=feedback,
        streak=signals.error_streak,
    )


def build_message(result: ScanResult) -> str:
    """Counts and the skill name only. Never quotes transcript text."""
    return (
        f"{HOOK_NAME}: this session holds {result.high} correction and "
        f"{result.med} praise or preference signal(s). "
        "You can run /reflect to review and approve what to keep."
    )


def build_friction_message(friction: Friction) -> str:
    """Fixed template: integers and the skill name only (AC-07)."""
    return (
        f"{HOOK_NAME}: this session shows friction (score {friction.score}, tier "
        f"{friction.tier}): {friction.denials} permission denial(s), "
        f"{friction.stop_feedback} Stop hook feedback message(s), and a longest "
        f"error streak of {friction.streak}. "
        "You can run /retrospective to review what went wrong."
    )


def status_line(result: ScanResult, outcome: str, friction_note: str = "") -> str:
    """Examined counts beside findings (ci-scripts MUST-12)."""
    budget = result.friction_budget
    tail = f", scan truncated at {result.stopped_on} budget" if result.stopped_on else ""
    if budget:
        tail += f", friction skipped: {budget} budget"
    tail += friction_note
    return (
        f"{HOOK_NAME}: {result.lines_scanned} lines scanned, {result.user_records} user records, "
        f"{result.human_turns} human turns, {result.high} HIGH, "
        f"{result.med} MED, {result.skipped_lines} skipped lines, "
        f"{result.dropped_records} records over event cap "
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
    default = getattr(failure_classifier, "FRICTION_TIER1_DEFAULT", FRICTION_FALLBACK_TIER1)
    threshold = parse_threshold(env, default)
    if threshold is None:
        return 0
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
        result = scan_transcript(handle, clock=clock, collect=failure_classifier is not None)
    friction = None if result.friction_budget else compute_friction(result, threshold)
    note = "" if failure_classifier is not None else ", friction skipped: classifier unavailable"
    if friction is not None:
        note = f", friction score {friction.score} tier {friction.tier}"
    wants_friction = friction is not None and friction.tier >= 1
    if not (has_signal(result) or wants_friction):
        print(status_line(result, "silent", note), file=stderr)
        return 0
    root = state_root or default_state_root(env)
    return _nudge_once(result, friction, session_id, (stdout, stderr), root, now, note)


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
    directory = _safe_marker_dir(state_root)
    if directory is None:
        return _fail_open(stderr, "marker directory unsafe")
    messages: list[str] = []
    if has_signal(result) and claim_marker(directory, session_id, result):
        messages.append(build_message(result))
    if friction is not None and friction.tier >= 1:
        if claim_friction_marker(directory, session_id, friction):
            messages.append(build_friction_message(friction))
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
