"""Citation verification using the Strategy pattern.

Each SourceType has a dedicated verifier callable. New source types
are added by registering a new verifier function, satisfying OCP.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from .models import (
    Citation,
    MemoryWithCitations,
    SourceType,
    VerificationResult,
)

# Exhaustiveness check: every SourceType must have a verifier registered.
# This runs at import time; see _VERIFIERS at module bottom.
_SOURCE_TYPES_EXPECTED = set(SourceType)

VerifierFn = Callable[[Citation, Path], VerificationResult]

_ISSUE_PR_PATTERN = re.compile(r"^#?\d+$")
_FILE_LINE_PATTERN = re.compile(r"^(?P<path>[^:]+)(?::(?P<line>\d+))?$")
_FUNCTION_PATTERN = re.compile(r"^(?P<path>[^:]+)::(?P<func>\w+)$")


def verify_citation(citation: Citation, repo_root: Path) -> VerificationResult:
    """Verify a single citation against the repository.

    Delegates to the appropriate strategy based on source_type.

    Args:
        citation: The citation to verify.
        repo_root: Root directory of the repository.

    Returns:
        VerificationResult with validity and reason.
    """
    verifier = _get_verifier(citation.source_type)
    return verifier(citation, repo_root)


def verify_all_citations(
    memory: MemoryWithCitations, repo_root: Path
) -> list[VerificationResult]:
    """Verify every citation in a memory.

    Args:
        memory: Memory containing citations to verify.
        repo_root: Root directory of the repository.

    Returns:
        List of VerificationResult for each citation.
    """
    return [verify_citation(c, repo_root) for c in memory.citations]


def find_stale_citations(
    memories: list[MemoryWithCitations], repo_root: Path
) -> list[tuple[str, Citation]]:
    """Find all stale or broken citations across memories.

    Args:
        memories: List of memories to scan.
        repo_root: Root directory of the repository.

    Returns:
        List of (memory_id, citation) pairs where verification failed.
    """
    stale: list[tuple[str, Citation]] = []
    for memory in memories:
        results = verify_all_citations(memory, repo_root)
        for result in results:
            if not result.is_valid:
                stale.append((memory.memory_id, result.citation))
    return stale


def _get_verifier(source_type: SourceType) -> VerifierFn:
    """Return the verification strategy for a given source type."""
    return _VERIFIERS.get(source_type, _verify_unknown)


def _validate_path_containment(
    relative_path: str, repo_root: Path
) -> tuple[Path | None, str | None]:
    """Resolve a path and verify it stays within repo_root (CWE-22 guard).

    Returns (resolved_path, None) on success or (None, error_reason) on failure.
    """
    candidate = (repo_root / relative_path).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return None, f"Path traversal blocked: {relative_path}"
    return candidate, None


def _verify_file(citation: Citation, repo_root: Path) -> VerificationResult:
    """Verify a file citation exists at the specified path and optional line."""
    match = _FILE_LINE_PATTERN.match(citation.target)
    if match is None:
        reason = f"Invalid file target format: {citation.target}"
        return VerificationResult.create(citation, False, reason)

    resolved, error = _validate_path_containment(match.group("path"), repo_root)
    if error or resolved is None:
        return VerificationResult.create(citation, False, error or "Invalid path")

    if not resolved.is_file():
        return VerificationResult.create(citation, False, f"File not found: {match.group('path')}")

    line_str = match.group("line")
    if line_str is not None:
        return _verify_file_line(citation, resolved, int(line_str))

    return VerificationResult.create(citation, True, "File exists")


def _verify_file_line(
    citation: Citation, file_path: Path, line_num: int
) -> VerificationResult:
    """Check that a file has at least the specified number of lines."""
    if line_num < 1:
        return VerificationResult.create(
            citation, False, f"Line number must be >= 1, got {line_num}"
        )

    try:
        with file_path.open(encoding="utf-8", errors="replace") as f:
            line_count = sum(1 for _ in f)
    except OSError as exc:
        return VerificationResult.create(citation, False, f"Cannot read file: {exc}")

    if line_num > line_count:
        return VerificationResult.create(
            citation, False, f"Line {line_num} exceeds file length ({line_count} lines)"
        )
    return VerificationResult.create(citation, True, f"File exists with line {line_num}")


def _verify_function(citation: Citation, repo_root: Path) -> VerificationResult:
    """Verify a function citation by checking file exists and function is defined."""
    match = _FUNCTION_PATTERN.match(citation.target)
    if match is None:
        return VerificationResult.create(
            citation, False, f"Invalid function target format: {citation.target}"
        )

    resolved, error = _validate_path_containment(match.group("path"), repo_root)
    if error or resolved is None:
        return VerificationResult.create(citation, False, error or "Invalid path")

    if not resolved.is_file():
        return VerificationResult.create(citation, False, f"File not found: {match.group('path')}")

    func_name = match.group("func")
    return _search_function_in_file(citation, resolved, func_name)


def _search_function_in_file(
    citation: Citation, file_path: Path, func_name: str
) -> VerificationResult:
    """Search for a function definition in a file.

    Detects both sync and async Python function definitions.
    """
    pattern = re.compile(rf"\b(?:async\s+)?def\s+{re.escape(func_name)}\b")
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return VerificationResult.create(citation, False, f"Cannot read file: {exc}")

    if pattern.search(content):
        return VerificationResult.create(citation, True, f"Function '{func_name}' found")
    return VerificationResult.create(citation, False, f"Function '{func_name}' not found in file")


def _verify_issue_pr(citation: Citation, _repo_root: Path) -> VerificationResult:
    """Validate issue/PR citation format without calling GitHub API."""
    if _ISSUE_PR_PATTERN.match(citation.target):
        return VerificationResult.create(citation, True, "Valid issue/PR reference format")
    return VerificationResult.create(citation, False, f"Invalid issue/PR format: {citation.target}")


def _verify_memory(citation: Citation, repo_root: Path) -> VerificationResult:
    """Verify a memory citation exists in .serena/memories/."""
    memories_dir = repo_root / ".serena" / "memories"
    target = citation.target
    if not target.endswith(".md"):
        target = target + ".md"

    resolved, error = _validate_path_containment(target, memories_dir)
    if error or resolved is None:
        return VerificationResult.create(citation, False, error or "Invalid path")

    if resolved.is_file():
        return VerificationResult.create(citation, True, "Memory file exists")
    return VerificationResult.create(citation, False, f"Memory file not found: {target}")


def _verify_adr(citation: Citation, repo_root: Path) -> VerificationResult:
    """Verify an ADR citation exists in .agents/architecture/."""
    adr_dir = repo_root / ".agents" / "architecture"
    target = citation.target
    if not target.endswith(".md"):
        target = target + ".md"

    resolved, error = _validate_path_containment(target, adr_dir)
    if error or resolved is None:
        return VerificationResult.create(citation, False, error or "Invalid path")

    if resolved.is_file():
        return VerificationResult.create(citation, True, "ADR file exists")
    return VerificationResult.create(citation, False, f"ADR file not found: {target}")


def _verify_url(citation: Citation, _repo_root: Path) -> VerificationResult:
    """Validate URL citation format without making HTTP requests."""
    if citation.target.startswith(("http://", "https://")):
        return VerificationResult.create(citation, True, "Valid URL format")
    return VerificationResult.create(citation, False, f"Invalid URL format: {citation.target}")


def _verify_unknown(citation: Citation, _repo_root: Path) -> VerificationResult:
    """Handle unknown source types."""
    return VerificationResult.create(
        citation, False, f"No verifier for source type: {citation.source_type.value}"
    )


_VERIFIERS: dict[SourceType, VerifierFn] = {
    SourceType.FILE: _verify_file,
    SourceType.FUNCTION: _verify_function,
    SourceType.ISSUE: _verify_issue_pr,
    SourceType.PR: _verify_issue_pr,
    SourceType.MEMORY: _verify_memory,
    SourceType.ADR: _verify_adr,
    SourceType.URL: _verify_url,
}

assert set(_VERIFIERS.keys()) == _SOURCE_TYPES_EXPECTED, (
    f"Verifier registry missing entries: {_SOURCE_TYPES_EXPECTED - set(_VERIFIERS.keys())}"
)
