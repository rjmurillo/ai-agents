"""Session reflection and confidence management.

Provides reusable functions for confidence recalculation,
skill candidate identification, session fact extraction,
and confidence decay. Used by the session_end hook.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .confidence import update_confidence_scores, update_confidence_scores_with_memories
from .serena_integration import load_memories

_SKILL_CONFIDENCE_THRESHOLD = 0.8
_SKILL_MIN_LINKS = 2


def reinforce_memories(
    memories_dir: Path, repo_root: Path
) -> dict[str, float]:
    """Recalculate confidence scores for all memories.

    Wraps update_confidence_scores to provide a stable interface
    for the reflection pipeline.

    Args:
        memories_dir: Path to .serena/memories/.
        repo_root: Repository root for citation verification.

    Returns:
        Dict mapping memory_id to updated confidence score.
    """
    return update_confidence_scores(memories_dir, repo_root)


def generate_skill_candidates(
    memories_dir: Path, repo_root: Path
) -> list[dict[str, str]]:
    """Identify high-confidence memories that could become skills.

    Governed mode: returns candidates without auto-promoting.
    A candidate must have confidence >= 0.8 and at least 2 links.

    Args:
        memories_dir: Path to .serena/memories/.
        repo_root: Repository root for confidence scoring.

    Returns:
        List of dicts with keys: memory_id, title, confidence, reason.
    """
    scores, memories = update_confidence_scores_with_memories(memories_dir, repo_root)
    memory_map = {m.memory_id: m for m in memories}

    candidates: list[dict[str, str]] = []
    for memory_id, score in scores.items():
        if score < _SKILL_CONFIDENCE_THRESHOLD:
            continue
        memory = memory_map.get(memory_id)
        if memory is None:
            continue
        if len(memory.links) < _SKILL_MIN_LINKS:
            continue
        candidates.append({
            "memory_id": memory_id,
            "title": memory.title,
            "confidence": f"{score:.3f}",
            "reason": f"confidence={score:.3f}, links={len(memory.links)}",
        })

    return candidates


def extract_session_facts(memories_dir: Path) -> list[str]:
    """Find memories updated during the current session (modified today).

    Args:
        memories_dir: Path to .serena/memories/.

    Returns:
        List of memory IDs modified today.
    """
    if not memories_dir.is_dir():
        return []

    today = datetime.now(UTC).date()
    updated: list[str] = []

    for md_file in memories_dir.rglob("*.md"):
        stat = md_file.stat()
        mod_date = datetime.fromtimestamp(stat.st_mtime, tz=UTC).date()
        if mod_date == today:
            updated.append(md_file.stem)

    return sorted(updated)


def apply_confidence_decay(
    memories_dir: Path,
    repo_root: Path,
    max_age_days: int = 90,
) -> list[str]:
    """Identify memories older than max_age with no recent verification.

    Does not modify files. Returns memory IDs that should be flagged
    for review or re-verification.

    Args:
        memories_dir: Path to .serena/memories/.
        repo_root: Repository root for confidence scoring.
        max_age_days: Maximum age in days before flagging.

    Returns:
        List of memory IDs that exceed the age threshold.
    """
    memories = load_memories(memories_dir)
    now = datetime.now(UTC)
    decayed: list[str] = []

    for memory in memories:
        age_days = (now - memory.updated_at).total_seconds() / 86400.0
        if age_days > max_age_days:
            decayed.append(memory.memory_id)

    return sorted(decayed)
