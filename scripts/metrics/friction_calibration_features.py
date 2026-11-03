"""Candidate friction features for the REQ-048 calibration replay.

Six per-Stop counts, each over the event and record prefix up to that Stop.
Counts only: no transcript text leaves this module. Every feature reads generic
Claude Code transcript behavior (error results, assistant prose, the Stop hook
continuation text), nothing repo-specific.

- ``denial_v2``: the shipped classifier's ``permission_denial`` count. Its
  markers exclude the bare word ``rejected``: a labeled sample of 15 found 0
  real denials.
- ``fp_repeat_max``: largest count of errored events sharing one fingerprint,
  using ``improved_fingerprint``; ``fp_repeat_max_old`` uses the shipped one.
- ``reply_repeat``: Stops whose final assistant prose nearly duplicates the
  previous Stop's.
- ``stop_feedback``: the shipped ``is_stop_feedback`` rule, counted per Stop.
- ``error_streak_max``: the shipped classifier's ``error_streak``.

``denial_v2``, ``stop_feedback``, and ``error_streak_max`` come from the shipped
functions, so the replay measures what the hook will compute. Different than the
shipped classifier: ``improved_fingerprint`` skips a leading ``Exit code N``
line, which otherwise collapses unrelated failures into one key. It,
``fp_repeat_max``, and ``reply_repeat`` stay calibration-only.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from scripts.failure_classifier import FailureEvent, classify, failure_fingerprint
from scripts.failure_classifier.transcript import _blocks, is_stop_feedback
from scripts.metrics.friction_calibration_text import is_injected

REPLY_SIMILARITY = 0.85
FEATURE_KEYS: tuple[str, ...] = (
    "denial_v2",
    "fp_repeat_max",
    "fp_repeat_max_old",
    "reply_repeat",
    "stop_feedback",
    "error_streak_max",
)

_EXIT_CODE_LINE = re.compile(r"^exit code -?\d+$", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def improved_fingerprint(tool: str, error: str) -> str | None:
    """``failure_fingerprint`` that skips a leading ``Exit code N`` line.

    With no non-blank line after the exit-code line, the exit-code line stays.
    """
    lines = [line for line in error.splitlines() if line.strip()]
    if len(lines) > 1 and _EXIT_CODE_LINE.match(lines[0].strip()):
        return failure_fingerprint(tool, "\n".join(lines[1:]))
    return failure_fingerprint(tool, error)


def normalize_reply(text: str) -> str:
    return _WHITESPACE.sub(" ", text.lower()).strip()


def near_duplicate(first: str, second: str) -> bool:
    """Both non-empty after normalizing, and ratio at or above the threshold."""
    a, b = normalize_reply(first), normalize_reply(second)
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= REPLY_SIMILARITY


def event_feature_series(
    events: Sequence[FailureEvent], event_counts: Sequence[int]
) -> list[dict[str, int]]:
    """Event-derived features at each prefix length in ``event_counts``.

    One pass over ``events`` for the fingerprint counts; the shipped
    ``classify`` runs on each distinct prefix for the other two.
    ``event_counts`` need not be sorted or unique.
    """
    wanted: dict[int, dict[str, int]] = {}
    new, old = Counter[str](), Counter[str]()
    targets = {min(c, len(events)) for c in event_counts}

    def snapshot(position: int) -> dict[str, int]:
        shipped = classify(events[:position])
        return {
            "denial_v2": shipped.permission_denial,
            "fp_repeat_max": max(new.values(), default=0),
            "fp_repeat_max_old": max(old.values(), default=0),
            "error_streak_max": shipped.error_streak,
        }

    if 0 in targets:
        wanted[0] = snapshot(0)
    for position, event in enumerate(events, start=1):
        if not event.ok:
            _count(new, improved_fingerprint(event.tool, event.error))
            _count(old, failure_fingerprint(event.tool, event.error))
        if position in targets:
            wanted[position] = snapshot(position)
    return [wanted[min(c, len(events))] for c in event_counts]


def _count(counter: Counter[str], key: str | None) -> None:
    if key is not None:
        counter[key] += 1


def last_prose(record: Mapping[str, Any]) -> str | None:
    """Final non-injected assistant text block of an ``assistant`` record."""
    if record.get("type") != "assistant":
        return None
    texts = [
        b["text"]
        for b in _blocks(record)
        if b.get("type") == "text" and isinstance(b.get("text"), str) and not is_injected(b["text"])
    ]
    return texts[-1] if texts else None


class RecordFeatures:
    """Record-derived features, filled while records stream past.

    Call ``observe`` for each non-sidechain record, and ``close_stop`` at each
    Stop boundary before the human-turn record is observed (and once at end of
    file). ``stops`` then holds one dict per Stop.
    """

    def __init__(self) -> None:
        self.stops: list[dict[str, int]] = []
        self._feedback = 0
        self._reply_repeat = 0
        self._prose = ""
        self._previous: str | None = None

    def observe(self, record: Mapping[str, Any]) -> None:
        prose = last_prose(record)
        if prose is not None:
            self._prose = prose
        elif is_stop_feedback(record):
            self._feedback += 1

    def close_stop(self) -> None:
        if self._previous is not None and near_duplicate(self._previous, self._prose):
            self._reply_repeat += 1
        self._previous = self._prose
        self._prose = ""
        self.stops.append({"reply_repeat": self._reply_repeat, "stop_feedback": self._feedback})


def add_stop_features(
    stops: list[dict[str, Any]], events: Sequence[FailureEvent], records: RecordFeatures
) -> None:
    """Merge all six features into each ``stops[i]`` entry, in place.

    ``records.close_stop`` must have run once per Stop, the end-of-file Stop
    included, so both series line up with ``stops``.
    """
    series = event_feature_series(events, [stop["event_count"] for stop in stops])
    for stop, from_events, from_records in zip(stops, series, records.stops, strict=True):
        stop.update(from_events)
        stop.update(from_records)
