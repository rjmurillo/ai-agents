"""Citation verification for Serena memories.

Implements just-in-time verification: check citations against the
current codebase at retrieval time, not continuous sync.
"""

from dataclasses import dataclass
from pathlib import Path

from .models import Citation, Memory


@dataclass
class VerificationResult:
    """Result of verifying all citations in a memory."""

    memory_id: str
    valid: bool
    total_citations: int
    valid_count: int
    stale_citations: list[Citation]
    confidence: float


def verify_citation(citation: Citation, repo_root: Path) -> Citation:
    """Verify a single citation against the codebase.

    Checks that the referenced file exists, the line number is valid,
    and the snippet matches the actual content at that line.
    """
    file_path = repo_root / citation.path

    if not file_path.exists():
        citation.valid = False
        citation.mismatch_reason = f"File not found: {citation.path}"
        return citation

    if citation.line is None:
        citation.valid = True
        return citation

    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        citation.valid = False
        citation.mismatch_reason = f"Cannot read file: {e}"
        return citation

    if citation.line < 1:
        citation.valid = False
        citation.mismatch_reason = f"Invalid line number: {citation.line} (must be >= 1)"
        return citation

    if citation.line > len(lines):
        citation.valid = False
        citation.mismatch_reason = (
            f"Line {citation.line} exceeds file length ({len(lines)})"
        )
        return citation

    actual_line = lines[citation.line - 1]

    if citation.snippet and citation.snippet not in actual_line:
        citation.valid = False
        citation.mismatch_reason = (
            f"Snippet mismatch at line {citation.line}. "
            f"Expected '{citation.snippet}', got '{actual_line.strip()}'"
        )
        return citation

    citation.valid = True
    return citation


def verify_memory(memory: Memory, repo_root: Path) -> VerificationResult:
    """Verify all citations in a memory."""
    stale = []
    valid_count = 0

    for citation in memory.citations:
        verify_citation(citation, repo_root)
        if citation.valid:
            valid_count += 1
        else:
            stale.append(citation)

    if memory.citations:
        confidence = valid_count / len(memory.citations)
    else:
        confidence = memory.confidence

    return VerificationResult(
        memory_id=memory.id,
        valid=len(stale) == 0,
        total_citations=len(memory.citations),
        valid_count=valid_count,
        stale_citations=stale,
        confidence=confidence,
    )


def verify_all_memories(
    memories_dir: Path, repo_root: Path
) -> list[VerificationResult]:
    """Batch verify all memories in a directory."""
    results = []

    for path in sorted(memories_dir.glob("*.md")):
        try:
            memory = Memory.from_file(path)
            if memory.citations:
                results.append(verify_memory(memory, repo_root))
        except Exception as e:
            print(f"Warning: Failed to parse {path}: {e}")

    return results
