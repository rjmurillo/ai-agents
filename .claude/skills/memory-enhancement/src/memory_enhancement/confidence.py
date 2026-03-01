"""Confidence scoring with temporal decay and trend analysis.

Tracks confidence history, applies time-based decay, and generates
dashboard reports for memory health monitoring.
"""

import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .models import Memory

DEFAULT_HALF_LIFE_DAYS = 30.0


@dataclass
class ConfidenceRecord:
    """A single confidence measurement at a point in time."""

    timestamp: datetime
    score: float
    valid_count: int
    total_count: int


def compute_decay(
    last_verified: datetime | None,
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Compute a decay factor based on time since last verification.

    Uses exponential decay: factor = 0.5 ^ (days_elapsed / half_life).
    Returns 1.0 when last_verified is None (no penalty without data).
    """
    if half_life_days <= 0:
        raise ValueError("half_life_days must be greater than zero")
    if last_verified is None:
        return 1.0
    if now is None:
        now = datetime.now(UTC)
    # Ensure timezone-aware comparison
    if last_verified.tzinfo is None:
        last_verified = last_verified.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    days_elapsed = max((now - last_verified).total_seconds() / 86400.0, 0.0)
    return math.pow(0.5, days_elapsed / half_life_days)


def apply_decay(
    memory: Memory,
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Apply temporal decay to a memory's confidence score.

    Returns the decayed confidence clamped to [0.0, 1.0].
    """
    factor = compute_decay(memory.last_verified, now, half_life_days)
    return max(0.0, min(1.0, memory.confidence * factor))


def record_confidence(
    memory: Memory,
    valid_count: int,
    total_count: int,
    timestamp: datetime | None = None,
) -> ConfidenceRecord:
    """Create a confidence record from verification results."""
    if timestamp is None:
        timestamp = datetime.now(UTC)
    score = valid_count / total_count if total_count > 0 else 0.5
    return ConfidenceRecord(
        timestamp=timestamp,
        score=score,
        valid_count=valid_count,
        total_count=total_count,
    )


def classify_trend(history: list[ConfidenceRecord]) -> str:
    """Classify the confidence trend from a history of records.

    Compares the average of the first half to the second half.
    Returns "improving", "stable", or "declining".
    """
    if len(history) < 2:
        return "stable"
    midpoint = len(history) // 2
    first_half = history[:midpoint]
    second_half = history[midpoint:]
    avg_first = sum(r.score for r in first_half) / len(first_half)
    avg_second = sum(r.score for r in second_half) / len(second_half)
    delta = avg_second - avg_first
    threshold = 0.05
    if delta > threshold:
        return "improving"
    if delta < -threshold:
        return "declining"
    return "stable"


def parse_confidence_history(
    raw_history: list[dict],
) -> list[ConfidenceRecord]:
    """Parse confidence_history from YAML frontmatter data."""
    records: list[ConfidenceRecord] = []
    for entry in raw_history:
        try:
            ts = entry.get("timestamp")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            elif not isinstance(ts, datetime):
                print(
                    f"Warning: Skipping history entry with invalid timestamp type: {entry}",
                    file=sys.stderr,
                )
                continue
            records.append(
                ConfidenceRecord(
                    timestamp=ts,
                    score=float(entry.get("score", 0.5)),
                    valid_count=int(entry.get("valid_count", 0)),
                    total_count=int(entry.get("total_count", 0)),
                )
            )
        except (ValueError, TypeError) as e:
            print(
                f"Warning: Skipping malformed history entry: {e} in {entry}",
                file=sys.stderr,
            )
            continue
    return records


def load_confidence_history(memory_path: Path) -> list[ConfidenceRecord]:
    """Load confidence history from a memory file's frontmatter."""
    import frontmatter

    post = frontmatter.load(str(memory_path))
    raw = post.metadata.get("confidence_history", [])
    if not raw:
        return []
    return parse_confidence_history(raw)


def render_dashboard(
    memories_dir: Path,
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> str:
    """Render a markdown dashboard of confidence scores with decay applied.

    Shows current confidence, decayed confidence, trend, and last verified date.
    """
    if now is None:
        now = datetime.now(UTC)

    entries: list[dict] = []
    if not memories_dir.exists():
        return "No memories directory found."

    for path in sorted(memories_dir.glob("*.md")):
        try:
            memory = Memory.from_file(path)
        except (yaml.YAMLError, UnicodeDecodeError, OSError, KeyError, ValueError):
            continue
        history = load_confidence_history(path)
        decayed = apply_decay(memory, now, half_life_days)
        trend = classify_trend(history)
        entries.append({
            "id": memory.id,
            "raw": memory.confidence,
            "decayed": decayed,
            "trend": trend,
            "last_verified": memory.last_verified,
            "history_len": len(history),
        })

    if not entries:
        return "No memories found."

    lines: list[str] = []
    lines.append("## Confidence Dashboard")
    lines.append("")
    lines.append("| Memory | Raw | Decayed | Trend | Last Verified | History |")
    lines.append("|--------|-----|---------|-------|---------------|---------|")

    for e in entries:
        lv = e["last_verified"].strftime("%Y-%m-%d") if e["last_verified"] else "never"
        trend_icon = {"improving": "+", "declining": "-", "stable": "="}
        icon = trend_icon.get(e["trend"], "?")
        lines.append(
            f"| {e['id']} "
            f"| {e['raw']:.0%} "
            f"| {e['decayed']:.0%} "
            f"| [{icon}] {e['trend']} "
            f"| {lv} "
            f"| {e['history_len']} records |"
        )

    lines.append("")

    low_conf = [e for e in entries if e["decayed"] < 0.5]
    if low_conf:
        lines.append(f"**Attention**: {len(low_conf)} memories below 50% decayed confidence.")
    else:
        lines.append("All memories above 50% decayed confidence.")

    return "\n".join(lines)


def render_dashboard_json(
    memories_dir: Path,
    now: datetime | None = None,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
) -> list[dict]:
    """Generate dashboard data as JSON-serializable list."""
    if now is None:
        now = datetime.now(UTC)

    entries: list[dict] = []
    if not memories_dir.exists():
        return entries

    for path in sorted(memories_dir.glob("*.md")):
        try:
            memory = Memory.from_file(path)
        except (yaml.YAMLError, UnicodeDecodeError, OSError, KeyError, ValueError):
            continue
        history = load_confidence_history(path)
        decayed = apply_decay(memory, now, half_life_days)
        trend = classify_trend(history)
        entries.append({
            "memory_id": memory.id,
            "raw_confidence": round(memory.confidence, 2),
            "decayed_confidence": round(decayed, 2),
            "trend": trend,
            "last_verified": (
                memory.last_verified.isoformat() if memory.last_verified else None
            ),
            "history_count": len(history),
        })

    return entries
