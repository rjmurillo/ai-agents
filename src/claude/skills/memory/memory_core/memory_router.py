#!/usr/bin/env python3
"""Unified memory access layer over Serena, the only memory backend.

Serena memories are plain committed markdown under `.serena/memories/`, so
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

# Default configuration
_config: dict[str, Any] = {
    "serena_path": ".serena/memories",
    "max_results": 10,
}


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
        logger.warning(
            "Failed to enumerate memory files in '%s': %s", memory_path, exc
        )
        return [], []

    lower_names = [
        f.relative_to(mem_dir).with_suffix("").as_posix().lower() for f in files
    ]

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
            weighted = stem_matches + DIRECTORY_MATCH_WEIGHT * (
                match_count - stem_matches
            )
            score = round((weighted / keyword_count) * 100, 2)
            current_file = files[idx]

            content = None
            content_hash = None

            if not skip_content:
                try:
                    content = current_file.read_text(encoding="utf-8")
                except OSError as exc:
                    logger.warning(
                        "Failed to read memory file '%s': %s", current_file, exc
                    )
                    continue
                content_hash = get_content_hash(content or "")

            results.append(
                MemoryResult(
                    name=current_file.relative_to(mem_dir)
                    .with_suffix("")
                    .as_posix(),
                    content=content,
                    source="Serena",
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
    return {
        "Serena": {
            "Available": Path(_config["serena_path"]).is_dir(),
            "Path": _config["serena_path"],
        },
        "Configuration": dict(_config),
    }


def search_memory(
    query: str,
    max_results: int = 10,
) -> list[MemoryResult]:
    """Search the Serena memory corpus.

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

    return invoke_serena_search(query, max_results=max_results)


def reset_caches() -> None:
    """Reset all module-level caches (for testing)."""
    global _file_list_cache
    _file_list_cache = _FileListCache()
