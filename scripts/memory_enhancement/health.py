"""Health reporting module for memory enhancement layer.

This module provides batch health checking and report generation
for memory citation validity and graph connectivity.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .citations import verify_all_memories, VerificationResult
from .graph import MemoryGraph


@dataclass
class HealthStats:
    """Aggregate statistics for memory health.

    Attributes:
        total_memories: Total memories processed
        memories_with_citations: Memories that have citations
        valid_memories: Memories with all valid citations
        stale_memories: Memories with at least one stale citation
        low_confidence_memories: Memories with confidence < 0.5
        average_confidence: Mean confidence across all memories
        orphaned_memories: Memories with no incoming/outgoing links (optional)
    """

    total_memories: int
    memories_with_citations: int
    valid_memories: int
    stale_memories: int
    low_confidence_memories: int
    average_confidence: float
    orphaned_memories: Optional[int] = None


def generate_health_report(
    memories_dir: Path,
    format: str = "markdown",
    include_graph_analysis: bool = False,
) -> str | dict:
    """Generate comprehensive health report for memories.

    Args:
        memories_dir: Path to .serena/memories directory
        format: Output format ("markdown" or "json")
        include_graph_analysis: Whether to analyze graph connectivity

    Returns:
        Formatted report as string (markdown) or dict (json)

    Raises:
        ValueError: If memories_dir doesn't exist or format is invalid
    """
    if not memories_dir.exists():
        raise ValueError(f"Memories directory not found: {memories_dir}")

    if format not in ("markdown", "json"):
        raise ValueError(f"Invalid format: {format}. Must be 'markdown' or 'json'")

    # Verify all memories with citations
    results = verify_all_memories(memories_dir)

    # Count total memories (including those without citations)
    total_memory_files = len(list(memories_dir.glob("*.md")))

    # Calculate statistics
    stats = _calculate_stats(results, total_memory_files)

    # Analyze graph connectivity if requested
    orphaned = []
    if include_graph_analysis:
        try:
            graph = MemoryGraph(memories_dir)
            orphaned = _find_orphaned_memories(graph)
            stats.orphaned_memories = len(orphaned)
        except Exception:
            # Graph analysis is optional, continue without it
            pass

    # Group results by category
    categorized = _categorize_results(results)

    # Generate report in requested format
    if format == "markdown":
        return _generate_markdown_report(stats, categorized, orphaned)
    else:
        return _generate_json_report(stats, categorized, orphaned)


def _calculate_stats(results: list[VerificationResult], total_memories: int) -> HealthStats:
    """Calculate aggregate statistics from verification results.

    Args:
        results: List of verification results for memories with citations
        total_memories: Total number of memory files

    Returns:
        HealthStats instance with calculated metrics
    """
    memories_with_citations = len(results)
    valid_memories = sum(1 for r in results if r.valid)
    stale_memories = memories_with_citations - valid_memories
    low_confidence = sum(1 for r in results if r.confidence < 0.5)

    # Calculate average confidence (only for memories with citations)
    if memories_with_citations > 0:
        avg_confidence = sum(r.confidence for r in results) / memories_with_citations
    else:
        avg_confidence = 1.0

    return HealthStats(
        total_memories=total_memories,
        memories_with_citations=memories_with_citations,
        valid_memories=valid_memories,
        stale_memories=stale_memories,
        low_confidence_memories=low_confidence,
        average_confidence=avg_confidence,
    )


def _categorize_results(
    results: list[VerificationResult],
) -> dict[str, list[VerificationResult]]:
    """Categorize verification results by status.

    Args:
        results: List of verification results

    Returns:
        Dictionary with categories: stale, low_confidence, no_citations
    """
    categories = defaultdict(list)

    for result in results:
        if not result.valid:
            categories["stale"].append(result)
        elif result.confidence < 0.5:
            categories["low_confidence"].append(result)

    return dict(categories)


def _find_orphaned_memories(graph: MemoryGraph) -> list[str]:
    """Find memories with no incoming or outgoing links.

    Args:
        graph: Loaded memory graph

    Returns:
        List of orphaned memory IDs
    """
    orphaned = []

    for memory_id, memory in graph.memories.items():
        # Check if memory has outgoing links
        has_outgoing = len(memory.links) > 0

        # Check if memory has incoming links
        has_incoming = any(
            memory_id in [link.target_id for link in m.links]
            for m in graph.memories.values()
            if m.id != memory_id
        )

        if not has_outgoing and not has_incoming:
            orphaned.append(memory_id)

    return orphaned


def _generate_markdown_report(
    stats: HealthStats,
    categorized: dict[str, list[VerificationResult]],
    orphaned: list[str],
) -> str:
    """Generate human-readable markdown report.

    Args:
        stats: Aggregate statistics
        categorized: Results grouped by category
        orphaned: List of orphaned memory IDs

    Returns:
        Markdown-formatted report
    """
    lines = [
        "# Memory Health Report",
        "",
        "## Summary",
        "",
        f"- **Total memories**: {stats.total_memories}",
        f"- **Memories with citations**: {stats.memories_with_citations}",
        f"- **Valid memories**: {stats.valid_memories} ✅",
        f"- **Stale memories**: {stats.stale_memories} ❌",
        f"- **Low confidence (<0.5)**: {stats.low_confidence_memories} ⚠️",
        f"- **Average confidence**: {stats.average_confidence:.2%}",
    ]

    if stats.orphaned_memories is not None:
        lines.append(f"- **Orphaned memories**: {stats.orphaned_memories} 🔗")

    # Stale memories section
    if "stale" in categorized and categorized["stale"]:
        lines.extend([
            "",
            "## ❌ Stale Memories",
            "",
            "These memories have citations that no longer point to valid locations:",
            "",
        ])

        for result in categorized["stale"]:
            lines.append(f"### {result.memory_id}")
            lines.append(f"- Confidence: {result.confidence:.2%}")
            lines.append(
                f"- Valid citations: {result.valid_count}/{result.total_citations}"
            )
            lines.append("")

            if result.stale_citations:
                lines.append("**Stale citations:**")
                for citation in result.stale_citations:
                    location = f"{citation.path}:{citation.line or ''}"
                    lines.append(f"- `{location}`")
                    lines.append(f"  - ❌ {citation.mismatch_reason}")
                lines.append("")

    # Low confidence section
    if "low_confidence" in categorized and categorized["low_confidence"]:
        lines.extend([
            "",
            "## ⚠️  Low Confidence Memories (<0.5)",
            "",
            "These memories have many stale citations and may need review:",
            "",
        ])

        for result in categorized["low_confidence"]:
            lines.append(f"- **{result.memory_id}**: {result.confidence:.2%} confidence")
            lines.append(
                f"  - {result.valid_count}/{result.total_citations} citations valid"
            )

    # Orphaned memories section
    if orphaned:
        lines.extend([
            "",
            "## 🔗 Orphaned Memories",
            "",
            "These memories have no links to or from other memories:",
            "",
        ])

        for memory_id in orphaned:
            lines.append(f"- {memory_id}")

    # Recommendations section
    if stats.stale_memories > 0 or (orphaned and len(orphaned) > 0):
        lines.extend([
            "",
            "## 💡 Recommendations",
            "",
        ])

        if stats.stale_memories > 0:
            lines.append(
                "- Update stale citations by running: "
                "`python -m memory_enhancement verify <memory-id>`"
            )
            lines.append(
                "- Consider removing memories with very low confidence (<0.3)"
            )

        if orphaned and len(orphaned) > 0:
            lines.append(
                "- Review orphaned memories and add relevant links to integrate them"
            )
            lines.append(
                "- Consider whether isolated memories should be tagged differently"
            )

    return "\n".join(lines)


def _generate_json_report(
    stats: HealthStats,
    categorized: dict[str, list[VerificationResult]],
    orphaned: list[str],
) -> dict:
    """Generate machine-readable JSON report.

    Args:
        stats: Aggregate statistics
        categorized: Results grouped by category
        orphaned: List of orphaned memory IDs

    Returns:
        Dictionary suitable for JSON serialization
    """
    report = {
        "summary": {
            "total_memories": stats.total_memories,
            "memories_with_citations": stats.memories_with_citations,
            "valid_memories": stats.valid_memories,
            "stale_memories": stats.stale_memories,
            "low_confidence_memories": stats.low_confidence_memories,
            "average_confidence": round(stats.average_confidence, 3),
        },
        "stale_memories": [],
        "low_confidence_memories": [],
    }

    if stats.orphaned_memories is not None:
        report["summary"]["orphaned_memories"] = stats.orphaned_memories
        report["orphaned_memories"] = orphaned

    # Add stale memories details
    if "stale" in categorized:
        for result in categorized["stale"]:
            report["stale_memories"].append({
                "memory_id": result.memory_id,
                "confidence": round(result.confidence, 3),
                "total_citations": result.total_citations,
                "valid_count": result.valid_count,
                "stale_citations": [
                    {
                        "path": c.path,
                        "line": c.line,
                        "snippet": c.snippet,
                        "mismatch_reason": c.mismatch_reason,
                    }
                    for c in result.stale_citations
                ],
            })

    # Add low confidence memories details
    if "low_confidence" in categorized:
        for result in categorized["low_confidence"]:
            report["low_confidence_memories"].append({
                "memory_id": result.memory_id,
                "confidence": round(result.confidence, 3),
                "total_citations": result.total_citations,
                "valid_count": result.valid_count,
            })

    return report
