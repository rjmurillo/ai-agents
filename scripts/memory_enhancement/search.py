"""Memory search engine with ripgrep primary, grep fallback.

Provides fast file-level search across memory directories using
ripgrep when available, falling back to grep. Results are ranked
by confidence score from the existing scoring infrastructure.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import find_repo_root
from .confidence import calculate_confidence
from .models import VerificationResult
from .serena_integration import load_memory
from .verification import STALE_REASON_MARKERS, verify_all_citations

_SEARCH_TIMEOUT = 5
_DEFAULT_MAX_RESULTS = 5
_SNIPPET_LENGTH = 200


@dataclass(frozen=True)
class SearchResult:
    """A ranked memory search result with confidence metadata."""

    memory_id: str
    file_path: Path
    confidence: float
    title: str
    snippet: str
    citation_status: str


def search_memories(
    query: str,
    memories_dir: Path,
    max_results: int = _DEFAULT_MAX_RESULTS,
    repo_root: Path | None = None,
) -> list[SearchResult]:
    """Search memories and return ranked results.

    Tries ripgrep first for speed. Falls back to grep.
    Returns empty list on failure (graceful degradation).

    Args:
        query: Search terms to match against memory content.
        memories_dir: Directory containing memory .md files.
        max_results: Maximum number of results to return.
        repo_root: Repository root for citation verification.
                   Defaults to detected repo root via find_repo_root.

    Returns:
        List of SearchResult sorted by confidence descending.
    """
    if not query or not query.strip():
        return []

    if not memories_dir.is_dir():
        return []

    effective_root = repo_root or find_repo_root(memories_dir) or memories_dir.parent.parent

    paths = _search_with_ripgrep(query, memories_dir)
    if paths is None:
        paths = _search_with_grep(query, memories_dir)
    if paths is None:
        return []

    return rank_results(paths, effective_root, max_results)


def rank_results(
    paths: list[Path],
    repo_root: Path,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> list[SearchResult]:
    """Load each matched file, score with confidence, and sort descending.

    Args:
        paths: File paths matching the search query.
        repo_root: Repository root for citation verification.
        max_results: Maximum results to return.

    Returns:
        Sorted list of SearchResult by confidence descending.
    """
    results: list[SearchResult] = []

    for file_path in paths:
        result = _score_memory_file(file_path, repo_root)
        if result is not None:
            results.append(result)

    results.sort(key=lambda r: r.confidence, reverse=True)
    return results[:max_results]


def _sanitize_term(term: str) -> str | None:
    """Return term if it contains only safe characters, else None.

    Allows alphanumeric, hyphens, underscores, and periods.
    Rejects terms with regex metacharacters to prevent injection.
    Escapes dots to prevent them being treated as regex wildcards.
    """
    if re.fullmatch(r"[\w.\-]+", term):
        return term.replace(".", r"\.")
    return None


def _split_query_terms(query: str) -> list[str]:
    """Split a multi-word query into sanitized individual terms.

    Returns a list of safe terms. Single-term queries return one element.
    """
    terms = query.strip().split()
    safe = [t for raw in terms if (t := _sanitize_term(raw)) is not None]
    return safe


def _search_with_ripgrep(query: str, memories_dir: Path) -> list[Path] | None:
    """Search using ripgrep. Returns None if rg is unavailable or fails.

    Multi-word queries use OR logic via multiple -e flags.
    """
    rg_path = shutil.which("rg")
    if rg_path is None:
        return None

    terms = _split_query_terms(query)
    if not terms:
        return None

    cmd: list[str] = [rg_path, "-il", "--no-ignore", "--glob", "*.md"]
    for term in terms:
        cmd.extend(["-e", term])
    cmd.extend(["--", str(memories_dir)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SEARCH_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode not in (0, 1):
        return None

    return _parse_file_list(result.stdout, memories_dir)


def _search_with_grep(query: str, memories_dir: Path) -> list[Path] | None:
    """Search using grep. Returns None if grep is unavailable or fails.

    Multi-word queries use OR logic via multiple -e flags.
    """
    grep_path = shutil.which("grep")
    if grep_path is None:
        return None

    terms = _split_query_terms(query)
    if not terms:
        return None

    cmd: list[str] = [grep_path, "-ril", "--include=*.md"]
    for term in terms:
        cmd.extend(["-e", term])
    cmd.extend(["--", str(memories_dir)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SEARCH_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode not in (0, 1):
        return None

    return _parse_file_list(result.stdout, memories_dir)


def _parse_file_list(stdout: str, memories_dir: Path) -> list[Path]:
    """Parse newline-separated file paths, filtering to those within memories_dir."""
    resolved_base = memories_dir.resolve()
    paths: list[Path] = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        candidate = Path(line).resolve()
        try:
            candidate.relative_to(resolved_base)
        except ValueError:
            continue
        paths.append(candidate)
    return paths


def _score_memory_file(file_path: Path, repo_root: Path) -> SearchResult | None:
    """Load a memory file, compute confidence, and build a SearchResult."""
    memory = load_memory(file_path)
    if memory is None:
        return None

    verification_results = verify_all_citations(memory, repo_root)
    confidence = calculate_confidence(memory, verification_results)
    citation_status = _determine_citation_status(verification_results)
    snippet = memory.content[:_SNIPPET_LENGTH]

    return SearchResult(
        memory_id=memory.memory_id,
        file_path=file_path,
        confidence=confidence,
        title=memory.title,
        snippet=snippet,
        citation_status=citation_status,
    )


def _determine_citation_status(results: list[VerificationResult]) -> str:
    """Classify overall citation status from verification results.

    Uses reason-based classification consistent with health.py:
    - "stale" means file exists but content changed (e.g., line count exceeded)
    - "broken" means target is missing entirely
    """
    if not results:
        return "unverified"

    all_valid = all(r.is_valid for r in results)
    if all_valid:
        return "verified"

    has_broken = False
    for r in results:
        if r.is_valid:
            continue
        reason_lower = r.reason.lower()
        if not any(marker in reason_lower for marker in STALE_REASON_MARKERS):
            has_broken = True

    if has_broken:
        return "broken"
    return "stale"
