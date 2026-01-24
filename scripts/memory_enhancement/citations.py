"""Citation verification logic for memory enhancement layer.

This module provides functions to verify that citations in memories
still point to valid locations in the codebase.
"""

import warnings
from dataclasses import dataclass
from pathlib import Path

from .models import Citation, Memory


@dataclass
class VerificationResult:
    """Result of verifying citations in a memory.

    Attributes:
        memory_id: ID of the verified memory
        valid: True if all citations are valid
        total_citations: Total number of citations
        valid_count: Number of valid citations
        stale_citations: List of citations that failed verification
        confidence: Calculated confidence score (0.0-1.0)
    """

    memory_id: str
    valid: bool
    total_citations: int
    valid_count: int
    stale_citations: list[Citation]
    confidence: float


def verify_citation(citation: Citation, repo_root: Path) -> Citation:
    """Verify a single citation points to a valid location.

    Args:
        citation: Citation to verify
        repo_root: Root directory of the repository

    Returns:
        Citation with updated valid and mismatch_reason fields
    """
    file_path = repo_root / citation.path

    # Check file existence
    if not file_path.exists():
        citation.valid = False
        citation.mismatch_reason = f"File not found: {citation.path}"
        return citation

    # If no line number specified, file existence is sufficient
    if citation.line is None:
        citation.valid = True
        citation.mismatch_reason = None
        return citation

    # Validate line number
    if citation.line < 1:
        citation.valid = False
        citation.mismatch_reason = f"Invalid line number: {citation.line} (must be >= 1)"
        return citation

    # Read file and check line bounds
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        citation.valid = False
        citation.mismatch_reason = f"Error reading file: {e}"
        return citation

    if citation.line > len(lines):
        citation.valid = False
        citation.mismatch_reason = (
            f"Line {citation.line} exceeds file length ({len(lines)} lines)"
        )
        return citation

    # Check snippet match if provided
    if citation.snippet:
        actual_line = lines[citation.line - 1]  # Convert to 0-indexed
        if citation.snippet not in actual_line:
            citation.valid = False
            citation.mismatch_reason = (
                f"Snippet not found in line {citation.line}. "
                f"Expected: '{citation.snippet}', Found: '{actual_line.strip()}'"
            )
            return citation

    # All checks passed
    citation.valid = True
    citation.mismatch_reason = None
    return citation


def verify_memory(memory: Memory, repo_root: Path = None) -> VerificationResult:
    """Verify all citations in a memory.

    Args:
        memory: Memory instance with citations to verify
        repo_root: Root directory of the repository (defaults to current directory)

    Returns:
        VerificationResult with metrics and stale citations
    """
    if repo_root is None:
        repo_root = Path.cwd()

    if not memory.citations:
        # No citations to verify, use existing confidence
        return VerificationResult(
            memory_id=memory.id,
            valid=True,
            total_citations=0,
            valid_count=0,
            stale_citations=[],
            confidence=memory.confidence,
        )

    # Verify each citation
    stale_citations = []
    valid_count = 0

    for citation in memory.citations:
        verified = verify_citation(citation, repo_root)
        if verified.valid:
            valid_count += 1
        else:
            stale_citations.append(verified)

    # Calculate confidence based on validity ratio
    confidence = valid_count / len(memory.citations) if memory.citations else memory.confidence

    return VerificationResult(
        memory_id=memory.id,
        valid=len(stale_citations) == 0,
        total_citations=len(memory.citations),
        valid_count=valid_count,
        stale_citations=stale_citations,
        confidence=confidence,
    )


def verify_all_memories(
    memories_dir: Path, repo_root: Path = None
) -> list[VerificationResult]:
    """Verify citations in all memory files.

    Args:
        memories_dir: Directory containing memory markdown files
        repo_root: Root directory of the repository (defaults to current directory)

    Returns:
        List of VerificationResult instances for memories with citations
    """
    if repo_root is None:
        repo_root = Path.cwd()

    results = []

    for memory_file in memories_dir.glob("*.md"):
        try:
            memory = Memory.from_serena_file(memory_file)

            # Skip memories without citations
            if not memory.citations:
                continue

            result = verify_memory(memory, repo_root)
            results.append(result)

        except Exception as e:
            warnings.warn(f"Error processing {memory_file}: {e}")
            continue

    return results
