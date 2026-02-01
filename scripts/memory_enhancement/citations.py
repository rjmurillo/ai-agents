"""Citation verification logic.

Validates that code references in memories still exist at expected locations.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

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
    """Verify a single citation against the codebase.

    Validates that the citation path stays within repo_root to prevent
    path traversal attacks (CWE-22).
    """
    # Resolve and validate path stays within repo_root (CWE-22 protection)
    try:
        file_path = (repo_root / citation.path).resolve()
        repo_root_resolved = repo_root.resolve()
        if not file_path.is_relative_to(repo_root_resolved):
            citation.valid = False
            citation.mismatch_reason = f"Path traversal detected: {citation.path}"
            return citation
    except (ValueError, OSError) as e:
        citation.valid = False
        citation.mismatch_reason = f"Invalid path: {e}"
        return citation

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
    except (OSError, IOError, UnicodeDecodeError) as e:
        citation.valid = False
        citation.mismatch_reason = f"File read error: {e}"

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


@dataclass
class VerifyAllResult:
    """Result of verifying all memories in a directory."""
    results: list[VerificationResult]
    parse_failures: int


def verify_all_memories(
    memories_dir: Path, repo_root: Path = None
) -> VerifyAllResult:
    """Verify all memories in a directory.

    Returns:
        VerifyAllResult containing verification results and count of parse failures.
        Callers can check parse_failures to detect if some files could not be processed.
    """
    repo_root = repo_root or Path.cwd()
    results = []
    parse_failures = 0

    for md_file in memories_dir.glob("*.md"):
        try:
            memory = Memory.from_serena_file(md_file)
            if memory.citations:
                results.append(verify_memory(memory, repo_root))
        except (OSError, IOError, UnicodeDecodeError, ValueError, KeyError, yaml.YAMLError) as e:
            print(f"Warning: Could not parse {md_file}: {e}", file=sys.stderr)
            parse_failures += 1

    return VerifyAllResult(results=results, parse_failures=parse_failures)
