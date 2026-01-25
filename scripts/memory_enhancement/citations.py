"""Citation verification logic.

Validates that code references in memories still exist at expected locations.
"""

from dataclasses import dataclass
from pathlib import Path

from .models import Citation, Memory


@dataclass
class VerificationResult:
    """Result of verifying a memory's citations."""
    memory_id: str
    valid: bool
    total_citations: int
    valid_count: int
    stale_citations: list[Citation]
    confidence: float


def verify_citation(citation: Citation, repo_root: Path) -> Citation:
    """Verify a single citation against the codebase."""
    file_path = repo_root / citation.path

    if not file_path.exists():
        citation.valid = False
        citation.mismatch_reason = f"File not found: {citation.path}"
        return citation

    if citation.line is None:
        citation.valid = True
        return citation

    try:
        lines = file_path.read_text().splitlines()
        if citation.line < 1:
            citation.valid = False
            citation.mismatch_reason = f"Invalid line number: {citation.line}"
            return citation
        if citation.line > len(lines):
            citation.valid = False
            citation.mismatch_reason = f"Line {citation.line} exceeds file length ({len(lines)} lines)"
            return citation

        actual_line = lines[citation.line - 1]
        if citation.snippet and citation.snippet not in actual_line:
            citation.valid = False
            citation.mismatch_reason = f"Snippet not found at line {citation.line}"
            return citation

        citation.valid = True
    except Exception as e:
        citation.valid = False
        citation.mismatch_reason = str(e)

    return citation


def verify_memory(memory: Memory, repo_root: Path = None) -> VerificationResult:
    """Verify all citations in a memory."""
    repo_root = repo_root or Path.cwd()

    if not memory.citations:
        return VerificationResult(
            memory_id=memory.id,
            valid=True,
            total_citations=0,
            valid_count=0,
            stale_citations=[],
            confidence=memory.confidence,
        )

    verified = [verify_citation(c, repo_root) for c in memory.citations]
    valid_count = sum(1 for c in verified if c.valid)
    stale = [c for c in verified if not c.valid]

    return VerificationResult(
        memory_id=memory.id,
        valid=len(stale) == 0,
        total_citations=len(verified),
        valid_count=valid_count,
        stale_citations=stale,
        confidence=valid_count / len(verified) if verified else memory.confidence,
    )


def verify_all_memories(memories_dir: Path, repo_root: Path = None) -> list[VerificationResult]:
    """Verify all memories in a directory."""
    repo_root = repo_root or Path.cwd()
    results = []

    for md_file in memories_dir.glob("*.md"):
        try:
            memory = Memory.from_serena_file(md_file)
            if memory.citations:
                results.append(verify_memory(memory, repo_root))
        except Exception as e:
            print(f"Warning: Could not parse {md_file}: {e}")

    return results
