#!/usr/bin/env python3
"""Hook: session_end - Reflection and confidence decay.

Recalculates confidence scores for every memory and prints a health summary
to stderr. The hook reads repository memory without modifying it.

Confidence is a pure function of citation validity, age, update recency, and
link count, recomputed on every read (``search._score_memory_file``). Nothing
reads a stored score, so writing one back bought nothing and cost the corpus:
the round trip through ``save_memory`` stripped every ``## Links`` block and
stamped ``created_at`` with wall clock on files that predate it, which is an
input to the freshness factor it claims to persist (issue #4011).

Hook Type: SessionEnd
Exit Codes:
    0 = always. SessionEnd cannot inject context: exit code 2 there only
        shows stderr to the user, and the session is already over.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from ..confidence import update_confidence_scores_with_memories
from ..models import HealthReport
from ..reflection import apply_confidence_decay, extract_session_facts
from ..stores import find_memory_root, repository_memory_dir, shadowed_notes_dir


def main() -> int:
    """Entry point for the session_end hook."""
    repo_root = _find_repo_root()
    if repo_root is None:
        return 0

    memories_dir = repository_memory_dir(repo_root)
    if memories_dir is None:
        return 0

    summary = _generate_reflection(memories_dir, repo_root)
    if summary:
        print(summary, file=sys.stderr)

    shadowed = shadowed_notes_dir(repo_root)
    if shadowed is not None:
        print(_shadowed_notes_warning(shadowed, repo_root), file=sys.stderr)

    return 0


def _shadowed_notes_warning(notes: Path, repo_root: Path) -> str:
    """Name the hidden notes folder and the manual migration (ADR-126)."""
    relative = notes.relative_to(repo_root.resolve())
    return (
        f"Memory: {relative} holds notes that recall no longer searches, because"
        " .serena/memories now exists. Move them with"
        f" `git mv {relative}/* .serena/memories/`."
    )


def _find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from start to the checkout or memory-store root."""
    return find_memory_root(start)


def _generate_reflection(memories_dir: Path, repo_root: Path) -> str:
    """Score every memory and produce a health summary. Writes nothing.

    Args:
        memories_dir: Path to a repository memory directory.
        repo_root: Repository root for verification.

    Returns:
        Formatted reflection string for stderr, or empty string.
    """
    from ..health import generate_health_report

    session_facts = extract_session_facts(memories_dir)

    _scores, memories = update_confidence_scores_with_memories(memories_dir, repo_root)

    # Identify memories needing re-verification due to age
    decayed = apply_confidence_decay(memories_dir, repo_root)

    # Pass pre-loaded memories to avoid redundant load + citation verification.
    report = generate_health_report(memories_dir, repo_root, preloaded_memories=memories)
    if report.total_memories == 0:
        return ""

    return _format_reflection(report, session_facts, decayed)


def _format_reflection(
    report: HealthReport,
    session_facts: Sequence[str] | None = (),
    decayed: list[str] | None = None,
) -> str:
    """Format the session reflection block for stderr.

    Args:
        report: HealthReport with health data and recommendations.
        session_facts: Memory IDs changed per git, or None when git cannot say.
        decayed: Memory IDs flagged for confidence decay.

    Returns:
        Formatted reflection string.
    """
    total = report.total_memories
    health_score = report.health_score
    stale = list(report.stale_memories)
    recommendations = list(report.recommendations)[:3]

    lines = [
        "<session-reflection>",
        "## Memory Health Summary",
        f"- Total: {total} memories, {health_score:.0%} health",
        f"- Stale: {len(stale)} need verification",
    ]

    if decayed:
        decayed_count = len(decayed)
        verb = "exceeds" if decayed_count == 1 else "exceed"
        lines.append(f"- Decayed: {decayed_count} {verb} the age threshold")

    if session_facts is None:
        lines.append("- Uncommitted memory changes: unknown (git unavailable)")
    elif session_facts:
        lines.append(f"- Uncommitted memory changes: {len(session_facts)} memories")

    if recommendations:
        lines.append(f"- Recommendations: {'; '.join(recommendations)}")

    lines.append("</session-reflection>")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
