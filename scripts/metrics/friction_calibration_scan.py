"""Per-session scan for the REQ-048 TASK-001 calibration replay.

One pass streams a top-level session transcript through the shipped
FailureClassifier (``scripts/failure_classifier``) and records, per Stop, the
four FrictionSignal counts. A Stop is the point just before each human turn
after the first, plus end of file (the hook fires at the end of each turn).

Reused, not copied:

- the classifier: ``events_from_records``, ``classify``, ``FailureSignals``;
- the live Stop hook's ``is_human_turn``, byte, line, and time budgets, and
  its bounded line reader, loaded from ``templates/hooks/Stop`` by path;
- consumer A's ``check_failures`` from the stuck-detection skill.

Output holds counts and ids only. Transcript text leaves this module only in
the candidate lists that ``friction_calibration_samples`` redacts before any
write.

Different than the hook: this scan reads files of any size, so a file over
``MAX_TRANSCRIPT_BYTES`` is measured and flagged ``within_budget: false``
instead of being skipped.
"""

from __future__ import annotations

import functools
import heapq
import json
import random
import re
import sys
import time
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from importlib import util
from pathlib import Path
from types import ModuleType
from typing import IO, Any, Generic, TypeVar

import scripts.failure_classifier as failure_classifier
from scripts.failure_classifier import (
    DENIAL_MARKERS,
    SHELL_TOOLS,
    FailureEvent,
    FailureSignals,
    check_command,
    classify,
    events_from_records,
    is_denial,
)
from scripts.failure_classifier.transcript import _blocks
from scripts.metrics.friction_calibration_features import (
    RecordFeatures,
    add_stop_features,
)
from scripts.metrics.friction_calibration_text import (
    SNIPPET_CHARS,
    matching_line,
    user_text,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = _REPO_ROOT / "templates" / "hooks" / "Stop" / "invoke_reflect_nudge.py"
LOOPS_PATH = _REPO_ROOT / "src" / "claude" / "skills" / "stuck-detection" / "failure_loops.py"

CHURN_THRESHOLD = 3  # consumer B whole-scan churn rule (REQ-048 Definitions)
DENIAL_LIKE_WORDS: tuple[str, ...] = ("denied", "not allowed", "blocked", "refused", "forbidden")
DENIAL_SAMPLE_MAX = 300
WORD_SAMPLE_MAX = 200
SHELL_SAMPLE_MAX = 400
FIRST_TS_LINE_LIMIT = 2000

_HEAD_PREFIX = re.compile(r"(?:cd\s+\S+\s*&&\s*|[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+")


@functools.cache
def hook() -> ModuleType:
    """The live Stop hook module, loaded by path (it is not a package)."""
    spec = util.spec_from_file_location("invoke_reflect_nudge", HOOK_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {HOOK_PATH}")
    module = util.module_from_spec(spec)
    sys.modules.setdefault("invoke_reflect_nudge", module)
    spec.loader.exec_module(module)
    return module


@functools.cache
def failure_loops() -> ModuleType:
    """Consumer A's module, bound to the same classifier this script uses.

    ``failure_loops`` imports ``failure_classifier`` from the plugin lib. Alias
    that name to ``scripts.failure_classifier`` first, so both read one source.
    """
    sys.modules.setdefault("failure_classifier", failure_classifier)
    spec = util.spec_from_file_location("failure_loops_calibration", LOOPS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {LOOPS_PATH}")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO timestamp (``Z`` allowed) to an aware UTC datetime."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def is_retro_invocation(record: Mapping[str, Any]) -> bool:
    """A Skill tool_use naming retrospective, or a slash-command user turn."""
    for block in _blocks(record) if record.get("type") == "assistant" else []:
        if block.get("type") != "tool_use" or str(block.get("name", "")).lower() != "skill":
            continue
        tool_input = block.get("input")
        if (
            isinstance(tool_input, Mapping)
            and "retrospective" in str(tool_input.get("skill", "")).lower()
        ):
            return True
    if record.get("type") != "user" or "toolUseResult" in record:
        return False
    text = user_text(record)
    return text.lstrip().startswith("/retrospective") or "<command-name>/retrospective" in text


@dataclass
class Tracker:
    """Side-channel counters filled while records stream past.

    ``stop_events[j]`` and ``stop_records[j]`` give the event and record
    counts before the j-th human-turn Stop. The end-of-file Stop is added by
    the caller. ``event_count`` mirrors the adapter's tool_use/tool_result
    pairing so a Stop maps to an event prefix without re-running the adapter;
    ``scan_session`` cross-checks it against ``len(events)``.
    """

    records: int = 0
    skipped: int = 0
    human_turns: int = 0
    event_count: int = 0
    first_ts: str | None = None
    stop_events: list[int] = field(default_factory=list)
    stop_records: list[int] = field(default_factory=list)
    retro_after_stop: int | None = None
    retro_seen: bool = False
    # Every Stop index after which a retrospective ran, in order, no repeats.
    retro_stops: list[int] = field(default_factory=list)
    # (record index, tool_use id) of each event's result, to cut an excerpt.
    event_records: list[tuple[int, str]] = field(default_factory=list)
    pending: set[str] = field(default_factory=set)
    paired: set[str] = field(default_factory=set)
    features: RecordFeatures = field(default_factory=RecordFeatures)

    def observe(self, record: Mapping[str, Any]) -> None:
        self.records += 1
        if self.first_ts is None:
            ts = record.get("timestamp")
            if isinstance(ts, str) and ts:
                self.first_ts = ts
        if record.get("isSidechain") is True:
            return
        self._pair(record)
        if hook().is_human_turn(record):
            self.human_turns += 1
            if self.human_turns > 1:
                self.stop_events.append(self.event_count)
                self.stop_records.append(self.records - 1)
                self.features.close_stop()
        self.features.observe(record)
        if is_retro_invocation(record):
            after = len(self.stop_events) - 1 if self.stop_events else None
            if not self.retro_seen:
                self.retro_seen = True
                self.retro_after_stop = after
            if after is not None and after not in self.retro_stops:
                self.retro_stops.append(after)

    def _pair(self, record: Mapping[str, Any]) -> None:
        # Mirrors events_from_records: conversation records only, and an id
        # pairs once even when a resumed session repeats it.
        record_type = record.get("type")
        for block in _blocks(record):
            kind = block.get("type")
            if kind == "tool_use" and record_type == "assistant":
                use_id, name = block.get("id"), block.get("name")
                if (
                    isinstance(use_id, str)
                    and use_id not in self.paired
                    and isinstance(name, str)
                    and name.strip()
                ):
                    self.pending.add(use_id)
            elif kind == "tool_result" and record_type == "user":
                use_id = block.get("tool_use_id")
                if isinstance(use_id, str) and use_id in self.pending:
                    self.pending.discard(use_id)
                    self.paired.add(use_id)
                    self.event_count += 1
                    self.event_records.append((self.records - 1, use_id))


def iter_records(handle: IO[str], tracker: Tracker) -> Iterator[dict[str, Any]]:
    """Yield decoded dict records; count malformed and over-long lines as skipped."""
    for line in hook()._bounded_lines(handle):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            tracker.skipped += 1
            continue
        if not isinstance(record, dict):
            tracker.skipped += 1
            continue
        tracker.observe(record)
        yield record


def stop_counts(signals: FailureSignals) -> dict[str, int]:
    """The four FrictionSignal counts (consumer B, whole-scan churn rule)."""
    return {
        "tool_error": signals.tool_error,
        "permission_denial": signals.permission_denial,
        "failed_retry": signals.failed_retry,
        "edit_churn": len(signals.churned_targets(CHURN_THRESHOLD)),
    }


def prefix_stops(
    events: list[FailureEvent], event_counts: list[int], whole: FailureSignals
) -> list[dict[str, Any]]:
    """One entry per Stop: classify the event prefix up to that Stop.

    ``whole`` is the classification of all events, reused for the final prefix.
    """
    cache: dict[int, dict[str, int]] = {len(events): stop_counts(whole)}
    stops: list[dict[str, Any]] = []
    for index, count in enumerate(event_counts):
        count = min(count, len(events))
        if count not in cache:
            cache[count] = stop_counts(classify(events[:count]))
        stops.append({"index": index, "event_count": count, **cache[count]})
    return stops


def broad_failed_retry(events: list[FailureEvent]) -> int:
    """The 2026-10-31 definition: a call repeating the previous call's key.

    REQ-048 Definitions: it counted the repeat of the previous call whatever
    its outcome (Q5's "identical back-to-back tool calls"). Keyless calls
    never match.
    """
    total = 0
    for previous, current in zip(events, events[1:], strict=False):
        key = current.progress_key
        if key is not None and key == previous.progress_key:
            total += 1
    return total


def replay_consumer_a(events: list[FailureEvent]) -> list[dict[str, Any]]:
    """Replay an agent calling check-failures after every event, defaults 3/3/20.

    Each call sees the last ``window`` events, which is what ``check_failures``
    keeps from ``events[:i+1]`` anyway, so the slice is equivalent and avoids
    quadratic copies. A window with fewer failures than the lowest threshold
    cannot fire either signal, so it is skipped without a call.
    Returns the first index per distinct (signal, fingerprint, target).
    """
    loops = failure_loops()
    repeat, churn, window = loops.DEFAULT_REPEAT, loops.DEFAULT_CHURN, loops.DEFAULT_WINDOW
    floor = min(repeat, churn)
    failed_prefix = [0]
    for event in events:
        failed_prefix.append(failed_prefix[-1] + (0 if event.ok else 1))
    seen: set[tuple[str, str, str | None]] = set()
    fires: list[dict[str, Any]] = []
    for i in range(len(events)):
        lo = max(0, i + 1 - window)
        if failed_prefix[i + 1] - failed_prefix[lo] < floor:
            continue
        result = loops.check_failures(
            events[lo : i + 1], repeat_threshold=repeat, churn_threshold=churn, window=window
        )
        for signal in result["signals"]:
            key = (signal["signal"], signal["fingerprint"], signal.get("target"))
            if key not in seen:
                seen.add(key)
                fires.append({"index": i, "signal": signal["signal"], "count": signal["count"]})
    return fires


T = TypeVar("T")
Triple = tuple[str, str, str]  # (session_id, marker or word, first error line)
Pair = tuple[str, str]  # (session_id, command)


class Pool(Generic[T]):
    """Uniform sample without replacement via the k smallest random keys.

    Each worker keeps its k smallest keys and the parent merges and keeps the
    k smallest overall, which is a uniform sample of everything offered.
    """

    def __init__(self, k: int, rng: random.Random) -> None:
        self._k = k
        self._rng = rng
        self._heap: list[tuple[float, int, T]] = []
        self._seq = 0

    def offer(self, item: T) -> None:
        self._seq += 1
        entry = (-self._rng.random(), self._seq, item)
        if len(self._heap) < self._k:
            heapq.heappush(self._heap, entry)
        else:
            heapq.heappushpop(self._heap, entry)

    def keyed(self) -> list[tuple[float, T]]:
        return [(-neg, item) for neg, _, item in self._heap]


def shell_command(event: FailureEvent) -> str:
    return check_command(event.input) or ""


def head_word(command: str) -> str:
    """First token of a command after leading ``cd x &&`` and VAR=val prefixes."""
    stripped = _HEAD_PREFIX.sub("", command.strip(), count=1)
    tokens = stripped.split()
    return tokens[0].lower()[:40] if tokens else ""


@dataclass
class Candidates:
    """Sampling state for one session. Holds raw text; the parent redacts it."""

    denial: Pool[Triple]
    word: Pool[Triple]
    shell: Pool[Pair]
    heads: Counter[str] = field(default_factory=Counter)

    @classmethod
    def for_session(cls, seed: int, session_id: str) -> Candidates:
        def pool(name: str, size: int) -> Pool[Any]:
            return Pool(size, random.Random(f"{seed}:{session_id}:{name}"))

        return cls(
            pool("denial", DENIAL_SAMPLE_MAX),
            pool("word", WORD_SAMPLE_MAX),
            pool("shell", SHELL_SAMPLE_MAX),
        )


def tally_events(
    events: list[FailureEvent], session_id: str, cands: Candidates
) -> tuple[dict[str, int], dict[str, int]]:
    """Count denial-marker hits and shell successes; offer sample candidates."""
    hits = dict.fromkeys(DENIAL_MARKERS, 0)
    shell = {"check": 0, "not_check": 0}
    for event in events:
        if not event.ok:
            _tally_error(event, session_id, hits, cands)
        elif event.tool in SHELL_TOOLS:
            _tally_shell(event, session_id, shell, cands)
    return hits, shell


def _tally_error(
    event: FailureEvent, session_id: str, hits: dict[str, int], cands: Candidates
) -> None:
    lowered = event.error.lower()
    matched = [marker for marker in DENIAL_MARKERS if marker in lowered]
    for marker in matched:
        hits[marker] += 1
    if matched:
        cands.denial.offer((session_id, matched[0], matching_line(event.error, matched[0])))
        return
    word = next((w for w in DENIAL_LIKE_WORDS if w in lowered), None)
    if word is not None and not is_denial(event.error):
        cands.word.offer((session_id, word, matching_line(event.error, word)))


def _tally_shell(
    event: FailureEvent, session_id: str, shell: dict[str, int], cands: Candidates
) -> None:
    if event.is_check:
        shell["check"] += 1
        return
    shell["not_check"] += 1
    command = shell_command(event)
    cands.heads[head_word(command)] += 1
    cands.shell.offer((session_id, command[:SNIPPET_CHARS]))


@dataclass
class SessionScan:
    """Result of scanning one file. ``row`` is None when the file is skipped."""

    status: str  # "scanned" | "skipped_window" | "skipped_no_timestamp" | "error"
    path: str
    row: dict[str, Any] | None = None
    cands: Candidates | None = None
    detail: str = ""


def first_timestamp(path: Path) -> str | None:
    """The first ``timestamp`` string in the file, within a bounded line count."""
    with path.open(encoding="utf-8", errors="replace") as handle:
        for _, line in zip(range(FIRST_TS_LINE_LIMIT), handle, strict=False):
            try:
                record = json.loads(line)
            except (ValueError, RecursionError):
                continue
            ts = record.get("timestamp") if isinstance(record, dict) else None
            if isinstance(ts, str) and ts:
                return ts
    return None


def in_window(first_ts: str, since: date, until: date) -> bool:
    parsed = parse_timestamp(first_ts)
    return parsed is not None and since <= parsed.date() <= until


def scan_session(path: Path, seed: int) -> SessionScan:
    """Stream one transcript once and build its sessions.jsonl row.

    ``scan_seconds`` covers read, decode, adapter, and one whole-file classify
    in this process. The per-Stop prefix replays, consumer A, and sampling run
    after the timer stops.
    """
    session_id = path.stem
    tracker = Tracker()
    started = time.perf_counter()
    with path.open(encoding="utf-8", errors="replace") as handle:
        events = events_from_records(iter_records(handle, tracker))
    final = classify(events)
    tracker.features.close_stop()
    scan_seconds = time.perf_counter() - started
    size = path.stat().st_size
    stop_events = [*tracker.stop_events, len(events)]
    cands = Candidates.for_session(seed, session_id)
    hits, shell = tally_events(events, session_id, cands)
    budgets = hook()
    stops = prefix_stops(events, stop_events, final)
    add_stop_features(stops, events, tracker.features)
    row: dict[str, Any] = {
        "session_id": session_id,
        "project": path.parent.name,
        "first_ts": tracker.first_ts,
        "bytes": size,
        "records": tracker.records,
        "events": len(events),
        "human_turns": tracker.human_turns,
        "stops": stops,
        "failed_retry_broad": broad_failed_retry(events),
        "retro_after_stop": tracker.retro_after_stop,
        "retro_stops": tracker.retro_stops,
        "scan_seconds": round(scan_seconds, 4),
        "within_budget": size <= budgets.MAX_TRANSCRIPT_BYTES
        and scan_seconds <= budgets.SCAN_BUDGET_SECONDS,
        "event_count_mismatch": tracker.event_count != len(events),
        "skipped_lines": tracker.skipped,
        "consumer_a": replay_consumer_a(events),
        "denial_hits": hits,
        "shell_success": shell,
    }
    return SessionScan("scanned", str(path), row, cands)


def scan_if_in_window(path: Path, since: date, until: date, seed: int) -> SessionScan:
    """Window-filter by the first record timestamp, then scan."""
    first_ts = first_timestamp(path)
    if first_ts is None or parse_timestamp(first_ts) is None:
        return SessionScan("skipped_no_timestamp", str(path))
    if not in_window(first_ts, since, until):
        return SessionScan("skipped_window", str(path))
    return scan_session(path, seed)


def safe_scan(path: Path, since: date, until: date, seed: int) -> SessionScan:
    """Worker entry: never raises, so one bad file cannot kill the pool."""
    try:
        return scan_if_in_window(path, since, until, seed)
    except Exception as error:  # reported as a counted error, never hidden
        return SessionScan("error", str(path), detail=type(error).__name__)
