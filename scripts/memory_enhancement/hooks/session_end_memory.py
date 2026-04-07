#!/usr/bin/env python3
"""Hook: session_end - Reflection and confidence decay.

Recalculates confidence scores for accessed memories.
Generates reflection summary via stderr.
"""

from __future__ import annotations

import sys
from pathlib import Path


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
    from ..confidence import update_confidence_scores
    from ..health import detect_stale_memories, generate_health_report

    scores = update_confidence_scores(memories_dir, repo_root)
    if not scores:
        return ""

    stale = detect_stale_memories(memories_dir, repo_root)
    report = generate_health_report(memories_dir, repo_root)

    return _format_reflection(scores, stale, report)


def _format_reflection(
    scores: dict[str, float],
    stale: list[str],
    report: object,
) -> str:
    """Format the session reflection block for stderr.

    Args:
        scores: Memory ID to confidence score mapping.
        stale: List of stale memory IDs.
        report: HealthReport object with health_score and recommendations.

    Returns:
        Formatted reflection string.
    """
    total = len(scores)
    health_score = getattr(report, "health_score", 0.0)
    recommendations = list(getattr(report, "recommendations", []))[:3]

    lines = [
        "<session-reflection>",
        "## Memory Health Summary",
        f"- Total: {total} memories, {health_score:.0%} health",
        f"- Stale: {len(stale)} need verification",
    ]

    if recommendations:
        lines.append(f"- Recommendations: {'; '.join(recommendations)}")

    lines.append("</session-reflection>")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
