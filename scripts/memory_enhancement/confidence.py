"""Confidence scoring for memories based on citation health.

Computes a 0.0-1.0 confidence score using citation validity,
memory age, update recency, and link count as weighted factors.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .models import MemoryWithCitations, VerificationResult
from .serena_integration import load_memories
from .verification import verify_all_citations

_WEIGHT_VALIDITY = 0.50
_WEIGHT_RECENCY = 0.25
_WEIGHT_LINKS = 0.15
_WEIGHT_FRESHNESS = 0.10

_MAX_AGE_DAYS = 365.0
_MAX_RECENCY_DAYS = 90.0
_MAX_LINKS = 10


def calculate_confidence(
    memory: MemoryWithCitations,
    verification_results: list[VerificationResult],
) -> float:
    """Calculate a confidence score for a memory.

    Factors (weights):
    - Citation validity ratio (50%)
    - Update recency (25%)
    - Link count (15%)
    - Memory freshness (10%)

    Args:
        memory: The memory to score.
        verification_results: Pre-computed verification results for this memory.

    Returns:
        Confidence score from 0.0 to 1.0.
    """
    validity = _validity_factor(verification_results)
    recency = _recency_factor(memory)
    links = _links_factor(memory)
    freshness = _freshness_factor(memory)

    raw_score = (
        _WEIGHT_VALIDITY * validity
        + _WEIGHT_RECENCY * recency
        + _WEIGHT_LINKS * links
        + _WEIGHT_FRESHNESS * freshness
    )
    return max(0.0, min(1.0, raw_score))


def update_confidence_scores(
    memories_dir: Path, repo_root: Path
) -> dict[str, float]:
    """Recalculate confidence scores for all memories.

    Args:
        memories_dir: Directory containing memory files.
        repo_root: Repository root for citation verification.

    Returns:
        Dictionary mapping memory_id to updated confidence score.
    """
    memories = load_memories(memories_dir)
    scores: dict[str, float] = {}

    for memory in memories:
        results = verify_all_citations(memory, repo_root)
        scores[memory.memory_id] = calculate_confidence(memory, results)

    return scores


def _validity_factor(results: list[VerificationResult]) -> float:
    """Score based on ratio of valid citations. Returns 1.0 if no citations."""
    if not results:
        return 1.0
    valid = sum(1 for r in results if r.is_valid)
    return valid / len(results)


def _recency_factor(memory: MemoryWithCitations) -> float:
    """Score based on how recently the memory was updated. Recent = higher."""
    now = datetime.now(UTC)
    days_since_update = max(0.0, (now - memory.updated_at).total_seconds() / 86400.0)
    return max(0.0, 1.0 - (days_since_update / _MAX_RECENCY_DAYS))


def _links_factor(memory: MemoryWithCitations) -> float:
    """Score based on number of outgoing links. More links = higher, capped."""
    return min(1.0, len(memory.links) / _MAX_LINKS)


def _freshness_factor(memory: MemoryWithCitations) -> float:
    """Score based on memory age. Newer memories score higher."""
    now = datetime.now(UTC)
    age_days = max(0.0, (now - memory.created_at).total_seconds() / 86400.0)
    return max(0.0, 1.0 - (age_days / _MAX_AGE_DAYS))
