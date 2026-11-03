"""Friction nudge logic that needs no I/O: threshold, tier, score, message (REQ-048 TASK-003).

The Stop hook ``invoke_reflect_nudge.py`` owns the transcript scan, the marker
files, and the output. Everything it decides from plain values lives here, so
the one definition of the weights, the tier 1 default, and the denial markers
stays in this package (AC-43).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, MutableSequence
from dataclasses import asdict, dataclass
from typing import Any

from .classifier import (
    FRICTION_TIER1_DEFAULT,
    classify,
    friction_score,
)
from .transcript import events_from_records, stop_feedback_count

THRESHOLD_ENV = "AI_AGENTS_RETRO_NUDGE_THRESHOLD"
OFF_VALUES = frozenset({"0", "off"})
MAX_TIER = 32
CONVERSATION_TYPES = frozenset({"assistant", "user"})
_INTEGER = re.compile(r"[+-]?[0-9]{1,18}")


@dataclass(frozen=True, slots=True)
class Friction:
    """The four counts of a FrictionScore, plus its tier. Integers only."""

    score: int
    tier: int
    denials: int
    stop_feedback: int
    streak: int


def parse_threshold(env: Mapping[str, str], default: int = FRICTION_TIER1_DEFAULT) -> int | None:
    """Return the tier 1 threshold, or None when the hook is off (AC-11 to AC-13).

    Off is the literal ``0`` or ``off`` (case-insensitive, whitespace ignored).
    ``00``, ``+0``, and ``-0`` are not off, and like a negative or non-integer
    value they select ``default``. Only ASCII digits parse as an integer.
    """
    raw = env.get(THRESHOLD_ENV)
    if raw is None:
        return default
    text = raw.strip()
    if text.lower() in OFF_VALUES:
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


def keeps_record(record: Mapping[str, Any]) -> bool:
    """True for a non-sidechain conversation record, the only kind the score reads."""
    return record.get("type") in CONVERSATION_TYPES and record.get("isSidechain") is not True


def collect_record(
    kept: MutableSequence[Mapping[str, Any]], record: Mapping[str, Any], cap: int
) -> int:
    """Append a scorable record to ``kept``. Returns 1 when ``cap`` dropped it, else 0."""
    if not keeps_record(record):
        return 0
    if len(kept) >= cap:
        return 1
    kept.append(record)
    return 0


def partial_budget(stopped_on: str, dropped: int) -> str:
    """Name the budget that makes a score partial (``time``, ``bytes``, ``events``), or empty."""
    return stopped_on or ("events" if dropped else "")


def friction_status(stopped_on: str, dropped: int, friction: Friction | None) -> str:
    """Status-line tail for the friction branch: the skip reason or the score."""
    budget = partial_budget(stopped_on, dropped)
    if budget:
        return f", friction skipped: {budget} budget"
    return f", friction score {friction.score} tier {friction.tier}" if friction else ""


def friction_marker_name(session_id: str, tier: int, version: int) -> str:
    """Marker file name keyed on (session, marker version, "friction", tier)."""
    key = f"{session_id}:{version}:friction:{tier}"
    return f"{session_id}.friction-{hashlib.sha256(key.encode()).hexdigest()[:16]}.json"


def friction_marker_body(friction: Friction, version: int) -> dict[str, int]:
    """Marker body: counts only, never transcript text."""
    return {"v": version, **asdict(friction)}


def compute_friction(records: Iterable[Mapping[str, Any]], threshold: int) -> Friction:
    """Score collected conversation records and derive the FrictionTier."""
    kept = tuple(records)
    signals = classify(events_from_records(kept))
    feedback = stop_feedback_count(kept)
    score = friction_score(signals, feedback)
    return Friction(
        score=score,
        tier=friction_tier(score, threshold),
        denials=signals.permission_denial,
        stop_feedback=feedback,
        streak=signals.error_streak,
    )


def build_friction_message(friction: Friction, prefix: str) -> str:
    """Fixed template: integers and the skill name only (AC-07)."""
    return (
        f"{prefix}: this session shows friction (score {friction.score}, tier "
        f"{friction.tier}): {friction.denials} permission denial(s), "
        f"{friction.stop_feedback} Stop hook feedback message(s), and a longest "
        f"error streak of {friction.streak}. "
        "You can run /retrospective to review what went wrong."
    )
