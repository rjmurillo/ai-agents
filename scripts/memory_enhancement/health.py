"""Health reporting and staleness detection for the memory system.

Aggregates verification results into a HealthReport with
actionable recommendations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .models import (
    HealthReport,
    MemoryWithCitations,
    VerificationResult,
)
from .serena_integration import load_memories
from .verification import verify_all_citations

# Reason substrings that indicate stale (content changed) vs broken (target gone)
_STALE_REASON_MARKERS = ("exceeds", "not found in file")


def generate_health_report(memories_dir: Path, repo_root: Path) -> HealthReport:
    """Generate a comprehensive health report for all memories.

    Loads memories once and verifies citations once, then passes results
    to all downstream functions to avoid redundant I/O.

    Args:
        memories_dir: Directory containing memory .md files.
        repo_root: Repository root for citation verification.

    Returns:
        HealthReport with aggregated statistics and recommendations.
    """
    memories = load_memories(memories_dir)
    all_results = _verify_all_memories(memories, repo_root)
    counts = _count_citation_statuses_from_results(all_results)
    stale = _detect_stale_from_results(memories, all_results, max_age_days=30)
    health_score = _calculate_health_score(counts, len(memories))
    recommendations = _generate_recommendations(counts, stale)

    return HealthReport(
        total_memories=len(memories),
        total_citations=counts["total"],
        valid_citations=counts["valid"],
        stale_citations=counts["stale"],
        broken_citations=counts["broken"],
        unverified_citations=counts["unverified"],
        health_score=health_score,
        stale_memories=stale,
        recommendations=recommendations,
    )


def detect_stale_memories(
    memories_dir: Path, repo_root: Path, max_age_days: int = 30
) -> list[str]:
    """Find memories that are older than max_age_days or have broken citations.

    Public API that loads memories from disk. For internal use with
    pre-loaded memories, see _detect_stale_from_loaded.

    Args:
        memories_dir: Directory containing memory .md files.
        repo_root: Repository root for citation verification.
        max_age_days: Maximum age in days before a memory is considered stale.

    Returns:
        List of stale memory IDs.
    """
    memories = load_memories(memories_dir)
    return _detect_stale_from_loaded(memories, repo_root, max_age_days)


def _detect_stale_from_loaded(
    memories: list[MemoryWithCitations],
    repo_root: Path,
    max_age_days: int = 30,
) -> list[str]:
    """Find stale memories from a pre-loaded list. Avoids redundant I/O."""
    now = datetime.now(UTC)
    stale_ids: list[str] = []

    for memory in memories:
        if _is_memory_stale(memory, now, max_age_days, repo_root):
            stale_ids.append(memory.memory_id)

    return sorted(stale_ids)


def _verify_all_memories(
    memories: list[MemoryWithCitations],
    repo_root: Path,
) -> dict[str, list[VerificationResult]]:
    """Verify all citations for all memories, returning results keyed by memory_id."""
    return {
        memory.memory_id: verify_all_citations(memory, repo_root)
        for memory in memories
    }


def _count_citation_statuses_from_results(
    all_results: dict[str, list[VerificationResult]],
) -> dict[str, int]:
    """Count citation statuses from pre-computed verification results."""
    counts = {"total": 0, "valid": 0, "stale": 0, "broken": 0, "unverified": 0}

    for results in all_results.values():
        for result in results:
            counts["total"] += 1
            status = _classify_result(result)
            counts[status] += 1

    return counts


def _detect_stale_from_results(
    memories: list[MemoryWithCitations],
    all_results: dict[str, list[VerificationResult]],
    max_age_days: int = 30,
) -> list[str]:
    """Find stale memories using pre-computed verification results."""
    now = datetime.now(UTC)
    stale_ids: list[str] = []

    for memory in memories:
        age_days = (now - memory.updated_at).days
        if age_days > max_age_days:
            stale_ids.append(memory.memory_id)
            continue
        results = all_results.get(memory.memory_id, [])
        if any(not r.is_valid for r in results):
            stale_ids.append(memory.memory_id)

    return sorted(stale_ids)


def format_report(report: HealthReport) -> str:
    """Format a HealthReport as human-readable markdown.

    Args:
        report: The health report to format.

    Returns:
        Markdown string representation.
    """
    lines = [
        "# Memory Health Report",
        "",
        f"**Health Score**: {report.health_score:.1%}",
        "",
        "## Citation Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Total memories | {report.total_memories} |",
        f"| Total citations | {report.total_citations} |",
        f"| Valid | {report.valid_citations} |",
        f"| Stale | {report.stale_citations} |",
        f"| Broken | {report.broken_citations} |",
        f"| Unverified | {report.unverified_citations} |",
    ]

    if report.stale_memories:
        lines.extend(["", "## Stale Memories", ""])
        for mid in report.stale_memories:
            lines.append(f"- {mid}")

    if report.recommendations:
        lines.extend(["", "## Recommendations", ""])
        for rec in report.recommendations:
            lines.append(f"- {rec}")

    return "\n".join(lines)


def _count_citation_statuses(
    memories: list[MemoryWithCitations], repo_root: Path
) -> dict[str, int]:
    """Verify all citations and count by status.

    Uses VerificationResult.reason to distinguish stale from broken.
    """
    counts = {"total": 0, "valid": 0, "stale": 0, "broken": 0, "unverified": 0}

    for memory in memories:
        results = verify_all_citations(memory, repo_root)
        for result in results:
            counts["total"] += 1
            status = _classify_result(result)
            counts[status] += 1

    return counts


def _classify_result(result: VerificationResult) -> str:
    """Classify a verification result into a status category.

    Uses the VerificationResult data directly instead of model status.
    Distinguishes stale (file exists but content changed, e.g. line count
    exceeded or function not found in file) from broken (target missing).
    """
    if result.is_valid:
        return "valid"
    reason_lower = result.reason.lower()
    # Stale: the file exists but the specific content has changed
    if any(marker in reason_lower for marker in _STALE_REASON_MARKERS):
        return "stale"
    return "broken"


def _calculate_health_score(counts: dict[str, int], total_memories: int) -> float:
    """Calculate overall health score from 0.0 to 1.0."""
    if total_memories == 0:
        return 1.0
    if counts["total"] == 0:
        return 1.0

    valid_ratio = counts["valid"] / counts["total"] if counts["total"] > 0 else 1.0
    broken_penalty = counts["broken"] / max(counts["total"], 1) * 0.5
    return max(0.0, min(1.0, valid_ratio - broken_penalty))


def _is_memory_stale(
    memory: MemoryWithCitations,
    now: datetime,
    max_age_days: int,
    repo_root: Path,
) -> bool:
    """Determine if a memory is stale by age or broken citations."""
    age_days = (now - memory.updated_at).days
    if age_days > max_age_days:
        return True

    results = verify_all_citations(memory, repo_root)
    return any(not r.is_valid for r in results)


def _generate_recommendations(counts: dict[str, int], stale: list[str]) -> list[str]:
    """Generate actionable recommendations based on health data."""
    recommendations: list[str] = []

    if counts["broken"] > 0:
        recommendations.append(
            f"Fix {counts['broken']} broken citation(s) to restore reference integrity."
        )
    if counts["unverified"] > 0:
        recommendations.append(
            f"Verify {counts['unverified']} unverified citation(s)."
        )
    if len(stale) > 0:
        recommendations.append(
            f"Review {len(stale)} stale memory/memories for relevance."
        )
    if counts["total"] == 0:
        recommendations.append("Add citations to memories for traceability.")

    return recommendations
