#!/usr/bin/env python3
"""Hook: session_end - Reflection and confidence decay.

Recalculates confidence scores for accessed memories.
Generates reflection summary via stderr.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..models import HealthReport
from ..reflection import apply_confidence_decay, extract_session_facts, reinforce_memories


def main() -> int:
    """Entry point for the session_end hook."""
    repo_root = _find_repo_root()
    if repo_root is None:
        return 0

    memories_dir = repo_root / ".serena" / "memories"
    if not memories_dir.is_dir():
        return 0

    summary = _generate_reflection(memories_dir, repo_root)
    if summary:
        print(summary, file=sys.stderr)
        return 2

    return 0


def _find_repo_root(start: Path | None = None) -> Path | None:
    """Walk up from start to find repo root. Delegates to shared utility."""
    from . import find_repo_root

    return find_repo_root(start)


def _generate_reflection(memories_dir: Path, repo_root: Path) -> str:
    """Run confidence recalculation and produce a health summary.

    Args:
        memories_dir: Path to .serena/memories/.
        repo_root: Repository root for verification.

    Returns:
        Formatted reflection string for stderr, or empty string.
    """
    from ..health import generate_health_report

    # Track session activity first (before any writes that update mtime)
    session_facts = extract_session_facts(memories_dir)

    # Recalculate confidence scores (may write to disk)
    reinforce_memories(memories_dir, repo_root)

    # Identify memories needing re-verification due to age
    decayed = apply_confidence_decay(memories_dir, repo_root)

    report = generate_health_report(memories_dir, repo_root)
    if report.total_memories == 0:
        return ""

    return _format_reflection(report, session_facts, decayed)


def _format_reflection(
    report: HealthReport,
    session_facts: list[str] | None = None,
    decayed: list[str] | None = None,
) -> str:
    """Format the session reflection block for stderr.

    Args:
        report: HealthReport with health data and recommendations.
        session_facts: Memory IDs updated this session.
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
        lines.append(f"- Decayed: {len(decayed)} exceed age threshold")

    if session_facts:
        lines.append(f"- Updated this session: {len(session_facts)} memories")

    if recommendations:
        lines.append(f"- Recommendations: {'; '.join(recommendations)}")

    lines.append("</session-reflection>")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
