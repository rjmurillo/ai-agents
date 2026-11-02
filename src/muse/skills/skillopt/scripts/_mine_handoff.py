"""session-patterns/1 handoff and per-host baseline validation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_STAT_KEYS = ("invocations", "corrections")


def _check_pattern(index: int, pattern: object, seen_ids: set[str]) -> None:
    """Validate one session-patterns/1 entry; raise ValueError on any defect."""
    if not isinstance(pattern, dict):
        raise ValueError(f"pattern {index} must be an object")
    pattern_id = pattern.get("id")
    if not isinstance(pattern_id, str) or not pattern_id or pattern_id in seen_ids:
        raise ValueError(f"pattern {index} has a missing or duplicate id")
    seen_ids.add(pattern_id)
    skill = pattern.get("skill")
    if not isinstance(skill, str) or not skill:
        raise ValueError(f"pattern {pattern_id} has no skill")
    sessions = pattern.get("sessions")
    if (
        not isinstance(sessions, list)
        or not sessions
        or not all(isinstance(value, str) and value for value in sessions)
    ):
        raise ValueError(f"pattern {pattern_id} needs nonempty session ids")
    prompts = pattern.get("prompts")
    if (
        not isinstance(prompts, list)
        or not prompts
        or not all(isinstance(value, str) and value.strip() for value in prompts)
    ):
        raise ValueError(f"pattern {pattern_id} prompts must be nonempty strings")
    invocations = pattern.get("invocations")
    corrections = pattern.get("corrections")
    if type(invocations) is not int or invocations < 1:
        raise ValueError(f"pattern {pattern_id} invocations must be a positive integer")
    if type(corrections) is not int or not 0 <= corrections <= invocations:
        raise ValueError(f"pattern {pattern_id} corrections exceed invocations")


def load_pattern_handoff(path: Path) -> list[dict[str, Any]]:
    """Load a validated `session-patterns/1` artifact from a companion skill."""
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:  # JSONDecodeError and UnicodeDecodeError
        raise ValueError(f"cannot read pattern handoff: {path}") from exc
    if not isinstance(document, dict) or document.get("schema") != "session-patterns/1":
        raise ValueError("pattern handoff must declare schema session-patterns/1")
    if "producer" in document and not isinstance(document["producer"], str):
        raise ValueError("pattern handoff producer must be a string when present")
    patterns = document.get("patterns")
    if not isinstance(patterns, list):
        raise ValueError("pattern handoff patterns must be a list")
    seen_ids: set[str] = set()
    for index, pattern in enumerate(patterns):
        _check_pattern(index, pattern, seen_ids)
    return patterns


def pattern_stats(patterns: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Reduce a companion skill's patterns to SkillOpt ranking statistics."""
    stats: dict[str, dict[str, int]] = {}
    for pattern in patterns:
        row = stats.setdefault(pattern["skill"], {"invocations": 0, "corrections": 0})
        row["invocations"] += pattern["invocations"]
        row["corrections"] += pattern["corrections"]
    return stats


def pattern_tasks(patterns: Iterable[dict[str, Any]], skill: str) -> list[str]:
    """Extract candidate prompts for one skill from a pattern handoff."""
    return [
        prompt.strip()
        for pattern in patterns
        if pattern["skill"] == skill
        for prompt in pattern["prompts"]
    ]


def merge_stats(parts: Iterable[dict[str, dict[str, int]]]) -> dict[str, dict[str, int]]:
    """Sum per-skill {invocations, corrections} across machines/sources."""
    total: dict[str, dict[str, int]] = {}
    for part in parts:
        for name, s in part.items():
            row = total.setdefault(name, {"invocations": 0, "corrections": 0})
            row["invocations"] += int(s.get("invocations", 0))
            row["corrections"] += int(s.get("corrections", 0))
    return total


def _check_baseline_row(path: Path, name: str, row: object) -> None:
    """One skill's counts: non-negative ints, and corrections never exceed invocations."""
    if not isinstance(row, dict):
        raise ValueError(f"baseline {path}: stats for {name!r} must be an object")
    for key in _STAT_KEYS:
        value = row.get(key, 0)
        if type(value) is not int or value < 0:
            raise ValueError(f"baseline {path}: {name}.{key} must be a non-negative integer")
    if row.get("corrections", 0) > row.get("invocations", 0):
        raise ValueError(f"baseline {path}: skill {name!r} has corrections > invocations")


def _load_baseline(path: Path) -> tuple[str, dict[str, dict[str, int]]]:
    """Read one `collect` baseline; any defect raises ValueError naming the file."""
    try:
        doc = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:  # JSONDecodeError and UnicodeDecodeError
        raise ValueError(f"cannot read baseline: {path}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("stats"), dict):
        raise ValueError(f"baseline {path} must be an object with a 'stats' object")
    host = doc.get("host", path.stem)
    if not isinstance(host, str):
        raise ValueError(f"baseline {path} host must be a string")
    for name, row in doc["stats"].items():
        _check_baseline_row(path, name, row)
    return host, doc["stats"]
