#!/usr/bin/env python3
"""Unified memory access layer over the repository's one memory store.

Per ADR-126 the store is `.serena/memories/` when that folder exists, else
`.project-toolkit/memory/notes/`. Both hold plain committed markdown, so
lexical search reads the working tree directly and cannot be unavailable the
way a network backend can.

This module implemented the ADR-037 two-backend router until the semantic
backend was decommissioned (issue #5574). With one backend there is no routing
decision, no availability probe, and no cross-source merge: a search is a
single keyword pass over the Serena corpus.

Exit codes (ADR-035):
    0 - Success
    1 - Logic error
    2 - Config error
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


DIRECTORY_MATCH_WEIGHT = 0.5
"""Credit for a keyword that matches only a parent directory, not the file name.

Matching moved from the bare stem to the relative path so nested memories become
reachable. That let a topic directory hand a perfect score to every file under
it, burying the top-level file the query actually named. Full credit for a stem
match and partial credit for a directory-only match keeps the recall and leaves
top-level scoring unchanged, since a top-level stem is its whole relative path.
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MemoryResult:
    """A single memory search result."""

    name: str
    content: str | None
    source: str
    score: float
    path: str | None = None
    hash: str | None = None
    id: int | None = None


# ---------------------------------------------------------------------------
# Module state
# ---------------------------------------------------------------------------


@dataclass
class _FileListCache:
    path: str = ""
    files: list[Path] = field(default_factory=list)
    lower_names: list[str] = field(default_factory=list)
    last_checked: float = 0.0
    cache_ttl: float = 10.0


_file_list_cache = _FileListCache()

# Default configuration. A `serena_path` of None resolves the store per call.
_config: dict[str, Any] = {
    "serena_path": None,
    "max_results": 10,
}

# ADR-126 store folders, in preference order, and the root markers. The
# memory_enhancement package and search_memory.py hold the same rule; the
# test_memory_root_parity tests keep the copies together.
STORE_DIRS = (Path(".serena", "memories"), Path(".project-toolkit", "memory", "notes"))
_ROOT_MARKER_DIRS = (Path(".serena", "memories"), Path(".project-toolkit", "memory"))


def _find_memory_root(start: Path) -> Path | None:
    for parent in (start, *start.parents):
        if (parent / ".git").exists() or any((parent / m).is_dir() for m in _ROOT_MARKER_DIRS):
            return parent
    return None


def resolve_memory_store(start: Path | None = None) -> Path | None:
    """Return the repository's one memory store, or None when it has none.

    The root is the nearest ancestor holding `.git`, `.serena/memories`, or
    `.project-toolkit/memory`. The store is the first of STORE_DIRS that
    exists and resolves inside that root.
    """
    # The consumer project comes first, as in search_memory.py; the current
    # directory is the fallback when the host sets no project directory.
    if start is None:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        start = Path(project_dir) if project_dir else Path.cwd()
    root = _find_memory_root(start.resolve())
    if root is None:
        return None
    for relative in STORE_DIRS:
        candidate = root / relative
        if candidate.is_dir():
            resolved = candidate.resolve()
            if resolved != root and resolved.is_relative_to(root):
                return resolved
    return None


def _store_path() -> str | None:
    configured = _config["serena_path"]
    if configured:
        return str(configured)
    store = resolve_memory_store()
    return str(store) if store else None


# ---------------------------------------------------------------------------
# Private functions
# ---------------------------------------------------------------------------


def get_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content for deduplication.

    Args:
        content: String content to hash.

    Returns:
        64-character lowercase hex hash.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_memory_files(memory_path: str) -> tuple[list[Path], list[str]]:
    """Get markdown files from memory path with caching.

    Returns:
        Tuple of (file paths, lowercase basenames).
    """
    now = time.monotonic()
    cache_valid = (
        _file_list_cache.path == memory_path
        and _file_list_cache.last_checked > 0
        and (now - _file_list_cache.last_checked) < _file_list_cache.cache_ttl
    )

    if cache_valid:
        logger.debug("Using cached file list (%d files)", len(_file_list_cache.files))
        return _file_list_cache.files, _file_list_cache.lower_names

    mem_dir = Path(memory_path)
    try:
        files = sorted(mem_dir.rglob("*.md"))
    except OSError as exc:
        logger.warning("Failed to enumerate memory files in '%s': %s", memory_path, exc)
        return [], []

    lower_names = [f.relative_to(mem_dir).with_suffix("").as_posix().lower() for f in files]

    _file_list_cache.path = memory_path
    _file_list_cache.files = files
    _file_list_cache.lower_names = lower_names
    _file_list_cache.last_checked = now
    logger.debug("Refreshed file list cache (%d files)", len(files))

    return files, lower_names


def invoke_serena_search(
    query: str,
    memory_path: str = ".serena/memories",
    max_results: int = 10,
    skip_content: bool = False,
) -> list[MemoryResult]:
    """Perform lexical search across Serena memory files.

    Searches .serena/memories/ for files matching query keywords.
    Scoring: based on percentage of query keywords matching in filename.

    Args:
        query: Search query string.
        memory_path: Path to Serena memories directory.
        max_results: Maximum results to return.
        skip_content: When True, skips file content reading and SHA-256 hashing.

    Returns:
        List of MemoryResult objects sorted by score descending.
    """
    mem_dir = Path(memory_path)
    if not mem_dir.is_dir():
        logger.debug("Memory path not found: %s", memory_path)
        return []
    # Label results by the store they came from, matching search_memory.py.
    source = "RepositoryNotes" if mem_dir.resolve().parts[-3:] == STORE_DIRS[1].parts else "Serena"

    # Extract keywords (>2 chars)
    lower_query = query.lower()
    keywords = [tok for tok in lower_query.split() if len(tok) > 2]
    if not keywords:
        logger.debug("No valid keywords extracted from query")
        return []

    keyword_count = len(keywords)

    files, lower_names = _get_memory_files(memory_path)
    results: list[MemoryResult] = []

    for idx, file_name in enumerate(lower_names):
        stem = file_name.rpartition("/")[2]
        stem_matches = sum(1 for kw in keywords if kw in stem)
        match_count = sum(1 for kw in keywords if kw in file_name)

        if match_count > 0:
            weighted = stem_matches + DIRECTORY_MATCH_WEIGHT * (match_count - stem_matches)
            score = round((weighted / keyword_count) * 100, 2)
            current_file = files[idx]

            content = None
            content_hash = None

            if not skip_content:
                try:
                    content = current_file.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.warning("Failed to read memory file '%s': %s", current_file, exc)
                    continue
                content_hash = get_content_hash(content or "")

            results.append(
                MemoryResult(
                    name=current_file.relative_to(mem_dir).with_suffix("").as_posix(),
                    content=content,
                    source=source,
                    score=score,
                    path=str(current_file),
                    hash=content_hash,
                )
            )

    results.sort(key=lambda r: r.score, reverse=True)
    results = results[:max_results]

    logger.debug("Serena search returned %d results", len(results))
    return results


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def get_memory_router_status() -> dict[str, Any]:
    """Return diagnostic information about the Memory Router.

    The second backend's status block and the `Cache` block are gone with it:
    the first reported a TCP probe that no longer runs, the second reported
    that probe's 30-second result cache.

    Returns:
        Dict with Serena and Configuration status.
    """
    store = _store_path()
    return {
        "Serena": {
            "Available": store is not None and Path(store).is_dir(),
            "Path": store or "",
        },
        "Configuration": dict(_config),
    }


def search_memory(
    query: str,
    max_results: int = 10,
) -> list[MemoryResult]:
    """Search the repository memory store (ADR-126).

    Main entry point for memory search. The two backend-selection parameters
    are gone: they chose between a lexical and a semantic store, and only the
    lexical one remains.

    Results carry `content` and `hash`, matching what the two-backend default
    path returned. The content read was skipped only by the lexical-only
    parameter, which no caller can pass any more.

    Args:
        query: Search query. Must match pattern ^[a-zA-Z0-9\\s\\-.,_()&:]+$
        max_results: Maximum results to return (1-100).

    Returns:
        List of MemoryResult objects.

    Raises:
        ValueError: If the query or max_results is invalid.
    """
    import re

    if not query or len(query) > 500:
        msg = "Query must be 1-500 characters"
        raise ValueError(msg)
    if not re.match(r"^[a-zA-Z0-9\s\-.,_()&:]+$", query):
        msg = "Query contains invalid characters"
        raise ValueError(msg)

    if max_results < 1 or max_results > 100:
        msg = "max_results must be between 1 and 100"
        raise ValueError(msg)

    logger.debug("search_memory: Query='%s', MaxResults=%d", query, max_results)

    store = _store_path()
    if store is None:
        logger.debug("search_memory: no repository memory store")
        return []
    return invoke_serena_search(query, memory_path=store, max_results=max_results)


def reset_caches() -> None:
    """Reset all module-level caches (for testing)."""
    global _file_list_cache
    _file_list_cache = _FileListCache()
