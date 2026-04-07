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
    from ..health import generate_health_report

    report = generate_health_report(memories_dir, repo_root)
    if report.total_memories == 0:
        return ""

    return _format_reflection(report)


def _format_reflection(report: object) -> str:
    """Format the session reflection block for stderr.

    Args:
        report: HealthReport object with health data and recommendations.

    Returns:
        Formatted reflection string.
    """
    total = getattr(report, "total_memories", 0)
    health_score = getattr(report, "health_score", 0.0)
    stale = list(getattr(report, "stale_memories", []))
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
