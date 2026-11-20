"""Memory search engine with ripgrep primary, grep fallback.

Provides fast file-level search across memory directories using
ripgrep when available, falling back to grep. Results are ranked
by confidence score from the existing scoring infrastructure.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import find_repo_root
from .confidence import calculate_confidence
from .models import MemoryWithCitations, VerificationResult
from .serena_integration import load_memory
from .verification import STALE_REASON_MARKERS, verify_citation

_SEARCH_TIMEOUT = 5
# Most candidate files loaded and scored per call. The file search matches any
# one term anywhere in a file, so a broad query can match hundreds of files.
MAX_CANDIDATES = 50
_DEFAULT_MAX_RESULTS = 5
_SNIPPET_LENGTH = 200
_STEM_LENGTH = 5


@dataclass(frozen=True)
class SearchResult:
    """A ranked memory search result with confidence metadata."""

    memory_id: str
    file_path: Path
    confidence: float
    title: str
    snippet: str
    citation_status: str
    relevance: float = 0.0


def query_relevance(query: str, label: str) -> float:
    """Return the fraction of distinct query terms that name the memory.

    ``label`` is the memory id basename plus title. Both sides split into words on
    every character outside ``[a-z0-9]``, so ``pr-autofix`` becomes
    ``pr`` and ``autofix``. A word matches when a label word equals it or
    shares its first ``_STEM_LENGTH`` characters (both at least that long),
    so "guards" matches "guard". A term matches when every one of its words
    matches. A compound term such as a memory id still counts as one term.
    Body text is ignored on purpose: the file search matches any term
    anywhere in a file, so a body hit says almost nothing about relevance
    (measured: 3 of 5 terms of an unrelated prompt appear in most large
    memories).

    Terms rejected by ``_sanitize_term``, or with no letters or digits, are
    ignored. Terms with the same words count once.

    Returns:
        A value in [0.0, 1.0]. 0.0 when the query has no usable terms.
    """
    terms = {words for t in _split_query_terms(query) if (words := _label_words(t))}
    if not terms:
        return 0.0
    label_words = _label_words(label)
    hits = sum(
        1 for words in terms if all(any(_stem_match(w, lw) for lw in label_words) for w in words)
    )
    return hits / len(terms)


def _label_words(text: str) -> tuple[str, ...]:
    """Return the lowercase ``[a-z0-9]`` runs of text, in order."""
    return tuple(re.findall(r"[a-z0-9]+", text.lower()))


def _stem_match(term: str, word: str) -> bool:
    """Return True if term equals word or both share a stem prefix."""
    if term == word:
        return True
    return (
        len(term) >= _STEM_LENGTH
        and len(word) >= _STEM_LENGTH
        and term[:_STEM_LENGTH] == word[:_STEM_LENGTH]
    )


def search_memories(
    query: str,
    memories_dir: Path,
    max_results: int = _DEFAULT_MAX_RESULTS,
    repo_root: Path | None = None,
    min_relevance: float = 0.0,
    deadline: float | None = None,
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
        min_relevance: Drop results whose query relevance (fraction of query
            terms naming the memory, see ``query_relevance``) is below this.
            Applied before the ``max_results`` cut. 0.0 keeps every match.
        deadline: ``time.monotonic()`` value after which no new work starts.
            The file-search timeouts shrink to the time left, and ranking
            returns what it has. None means no deadline.

    Returns:
        List of SearchResult sorted by relevance, then confidence, descending.
    """
    if not query or not query.strip():
        return []

    if not memories_dir.is_dir():
        return []

    effective_root = repo_root or find_repo_root(memories_dir) or memories_dir.parent.parent

    paths = _search_with_ripgrep(query, memories_dir, deadline)
    if paths is None:
        paths = _search_with_grep(query, memories_dir, deadline)
    if paths is None:
        return []

    return rank_results(
        paths,
        effective_root,
        max_results,
        memories_dir=memories_dir,
        query=query,
        min_relevance=min_relevance,
        deadline=deadline,
    )


def _time_left(deadline: float | None) -> float | None:
    """Seconds until *deadline* (never negative), or None when there is none."""
    return None if deadline is None else max(0.0, deadline - time.monotonic())


def _search_timeout(deadline: float | None) -> float | None:
    """The subprocess timeout that fits the deadline, or None when none is left."""
    left = _time_left(deadline)
    if left is None:
        return _SEARCH_TIMEOUT
    return min(_SEARCH_TIMEOUT, left) if left > 0 else None


def _bounded_candidates(paths: list[Path], query: str, limit: int) -> list[Path]:
    """Keep at most *limit* paths in a deterministic order.

    Order is stem relevance to the query, best first, then path. The stem is
    the cheap part of the label ``_score_memory_file`` scores, so no file is
    read. A memory that matches only through its frontmatter title can fall
    outside the cut when more than *limit* files match.
    """
    ordered = sorted(paths, key=lambda p: (-query_relevance(query, p.stem), str(p)))
    return ordered[:limit]


def rank_results(
    paths: list[Path],
    repo_root: Path,
    max_results: int = _DEFAULT_MAX_RESULTS,
    memories_dir: Path | None = None,
    query: str = "",
    min_relevance: float = 0.0,
    deadline: float | None = None,
    max_candidates: int = MAX_CANDIDATES,
) -> list[SearchResult]:
    """Load each matched file, score relevance and confidence, drop results
    below ``min_relevance``, and sort descending.

    Args:
        paths: File paths matching the search query.
        repo_root: Repository root for citation verification.
        max_results: Maximum results to return.
        memories_dir: Root memories directory.  When provided, each result's
            ``memory_id`` is path-qualified so it matches ``verify --memory-id``.
        query: Query used to compute each result's ``relevance``. Empty
            leaves relevance at 0.0.
        min_relevance: Drop results with relevance below this value before
            truncating to ``max_results``.
        deadline: ``time.monotonic()`` value after which no further file is
            loaded and citation checks are skipped (status "unverified").
        max_candidates: Most files loaded and scored, chosen by
            ``_bounded_candidates``.

    Returns:
        Sorted list of SearchResult by relevance, then confidence, descending.
    """
    results: list[SearchResult] = []

    for file_path in _bounded_candidates(paths, query, max_candidates):
        if _time_left(deadline) == 0.0:
            break
        result = _score_memory_file(file_path, repo_root, memories_dir, query, deadline)
        if result is not None and result.relevance >= min_relevance:
            results.append(result)

    results.sort(key=lambda r: (r.relevance, r.confidence), reverse=True)
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


def _search_with_ripgrep(
    query: str, memories_dir: Path, deadline: float | None = None
) -> list[Path] | None:
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

    timeout = _search_timeout(deadline)
    if timeout is None:
        return None

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode not in (0, 1):
        return None

    return _parse_file_list(result.stdout, memories_dir)


def _search_with_grep(
    query: str, memories_dir: Path, deadline: float | None = None
) -> list[Path] | None:
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

    timeout = _search_timeout(deadline)
    if timeout is None:
        return None

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
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


def _score_memory_file(
    file_path: Path,
    repo_root: Path,
    memories_dir: Path | None = None,
    query: str = "",
    deadline: float | None = None,
) -> SearchResult | None:
    """Load a memory file, compute confidence, and build a SearchResult."""
    memory = load_memory(file_path, memories_dir)
    if memory is None:
        return None

    verification_results = _verify_within(memory, repo_root, deadline)
    confidence = calculate_confidence(memory, verification_results)
    citation_status = _determine_citation_status(verification_results)
    snippet = memory.content[:_SNIPPET_LENGTH]
    # Score the file stem only. A folder segment such as "github/" would give
    # every memory in that folder a hit for a prompt that names the folder.
    # The stem avoids splitting memory_id, whose separator is OS specific.
    basename = file_path.stem

    return SearchResult(
        memory_id=memory.memory_id,
        file_path=file_path,
        confidence=confidence,
        title=memory.title,
        snippet=snippet,
        citation_status=citation_status,
        relevance=query_relevance(query, f"{basename} {memory.title}"),
    )


def _verify_within(
    memory: MemoryWithCitations, repo_root: Path, deadline: float | None
) -> list[VerificationResult]:
    """Verify each citation while time remains.

    Out of time means no verification at all, not a partial one, so the status
    reads "unverified" and a half-checked memory never reads "verified".
    """
    results: list[VerificationResult] = []
    for citation in memory.citations:
        if _time_left(deadline) == 0.0:
            return []
        results.append(verify_citation(citation, repo_root))
    return results


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
