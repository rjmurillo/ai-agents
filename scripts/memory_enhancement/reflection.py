"""Session reflection and confidence management.

Provides reusable functions for confidence recalculation,
skill candidate identification, session fact extraction,
and confidence decay. Used by the session_end hook.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .confidence import update_confidence_scores_with_memories
from .serena_integration import load_memories

_SKILL_CONFIDENCE_THRESHOLD = 0.8
_SKILL_MIN_LINKS = 2

# Seconds allowed for the git status lookup. SessionEnd is not a latency path,
# so this only trips on a hung git.
_GIT_STATUS_TIMEOUT_SECONDS = 5

_SESSION_FACT_SKIP_NAMES = frozenset({"README.md", "CLAUDE.md"})


def generate_skill_candidates(memories_dir: Path, repo_root: Path) -> list[dict[str, str]]:
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
        candidates.append(
            {
                "memory_id": memory_id,
                "title": memory.title,
                "confidence": f"{score:.3f}",
                "reason": f"confidence={score:.3f}, links={len(memory.links)}",
            }
        )

    return candidates


def _changed_paths(memories_dir: Path) -> list[str] | None:
    """Paths under ``memories_dir`` that differ from HEAD or are untracked.

    Returns None when git cannot answer: git missing, not a repository, a
    non-zero exit, or a timeout. Parses ``git status --porcelain -z`` so odd
    file names survive; a rename entry carries the old path as an extra field,
    which is skipped.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(
            [
                git,
                "-C",
                str(memories_dir),
                "status",
                "--porcelain",
                "-z",
                "--untracked-files=all",
                "--",
                ".",
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_STATUS_TIMEOUT_SECONDS,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    paths: list[str] = []
    fields = iter(result.stdout.split("\0"))
    for field in fields:
        if len(field) < 4:
            continue
        status, path = field[:2], field[3:]
        if "R" in status or "C" in status:
            next(fields, None)  # old path of a rename or copy
        paths.append(path)
    return paths


def extract_session_facts(memories_dir: Path) -> list[str] | None:
    """Find memories changed during the current session, according to git.

    A memory counts as changed when its file differs from ``HEAD`` or is
    untracked (``git status --porcelain``). File mtime is not used: a fresh
    checkout stamps every file with the same time, which once reported all
    1068 memories as updated (Issue #7227).

    Args:
        memories_dir: Path to .serena/memories/.

    Returns:
        Sorted memory IDs with changes, an empty list when the directory is
        missing or clean, or None when git cannot answer (the figure is
        unknown, not zero).
    """
    if not memories_dir.is_dir():
        return []

    paths = _changed_paths(memories_dir)
    if paths is None:
        return None

    updated: set[str] = set()
    for raw in paths:
        path = Path(raw)
        if path.suffix != ".md" or path.name in _SESSION_FACT_SKIP_NAMES:
            continue
        updated.add(path.stem)
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
