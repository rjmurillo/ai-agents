#!/usr/bin/env python3
"""Unified memory access layer with Serena-first routing and Forgetful augmentation.

Implements ADR-037 Memory Router Architecture for Phase 2A.
Provides a unified interface for memory search across:
- Serena (lexical, file-based, always available)
- Forgetful (semantic, vector-based, optional augmentation)

Routing strategy:
1. Always query Serena first (canonical source)
2. If Forgetful available and not lexical_only, augment with semantic results
3. Deduplicate using SHA-256 content hashing
4. Return merged results with source attribution

Exit codes (ADR-035):
    0 - Success
    1 - Logic error
    2 - Config error
    3 - External error (Forgetful unavailable)
"""

from __future__ import annotations

import hashlib
import json
import logging
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
class _HealthCache:
    available: bool = False
    last_checked: float = 0.0
    cache_ttl: float = 30.0


@dataclass
class _FileListCache:
    path: str = ""
    files: list[Path] = field(default_factory=list)
    lower_names: list[str] = field(default_factory=list)
    last_checked: float = 0.0
    cache_ttl: float = 10.0


_health_cache = _HealthCache()
_file_list_cache = _FileListCache()

# Default configuration
_config: dict[str, Any] = {
    "serena_path": ".serena/memories",
    "forgetful_port": 8020,
    "forgetful_timeout": 0.5,  # seconds
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
        files = sorted(mem_dir.glob("*.md"))
    except OSError as exc:
        logger.warning(
            "Failed to enumerate memory files in '%s': %s", memory_path, exc
        )
        return [], []

    lower_names = [f.stem.lower() for f in files]

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
        match_count = sum(1 for kw in keywords if kw in file_name)

        if match_count > 0:
            score = round((match_count / keyword_count) * 100, 2)
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
                    name=current_file.stem,
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


def invoke_forgetful_search(
    query: str,
    endpoint: str = "http://localhost:8020/mcp",
    max_results: int = 10,
) -> list[MemoryResult]:
    """Perform semantic search via Forgetful MCP HTTP endpoint.

    Uses JSON-RPC 2.0 protocol via MCP tool invocation.

    Args:
        query: Search query string.
        endpoint: HTTP endpoint URL.
        max_results: Maximum results to return.

    Returns:
        List of MemoryResult objects.
    """
    results: list[MemoryResult] = []

    request_body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "memory_search",
            "arguments": {
                "query": query,
                "limit": max_results,
            },
        },
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            endpoint,
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))

        result_obj = response_data.get("result")
        if result_obj and result_obj.get("content"):
            for item in result_obj["content"]:
                if item.get("type") == "text" and item.get("text"):
                    try:
                        memories = json.loads(item["text"])
                        if isinstance(memories, list):
                            for memory in memories:
                                content = (
                                    memory.get("content")
                                    or memory.get("text")
                                    or ""
                                )
                                results.append(
                                    MemoryResult(
                                        id=memory.get("id", 0),
                                        name=memory.get("title", "Unknown"),
                                        content=content,
                                        source="Forgetful",
                                        score=memory.get(
                                            "score",
                                            memory.get("similarity", 0),
                                        ),
                                        hash=get_content_hash(content),
                                    )
                                )
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "Forgetful returned unparseable response: %s", exc
                        )

    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Forgetful search unavailable: %s", exc)
        return []

    logger.debug("Forgetful search returned %d results", len(results))
    return results


def merge_memory_results(
    serena_results: list[MemoryResult] | None = None,
    forgetful_results: list[MemoryResult] | None = None,
    max_results: int = 10,
) -> list[MemoryResult]:
    """Merge and deduplicate results from multiple sources.

    Uses SHA-256 content hashing to identify duplicates.
    Serena results take priority (appear first, are the canonical source).

    Args:
        serena_results: Results from Serena search.
        forgetful_results: Results from Forgetful search.
        max_results: Maximum total results to return.

    Returns:
        List of merged, deduplicated results.
    """
    if serena_results is None:
        serena_results = []
    if forgetful_results is None:
        forgetful_results = []

    merged: list[MemoryResult] = []
    seen_hashes: set[str] = set()

    # Add Serena results first (canonical)
    for result in serena_results:
        if result.hash is None:
            merged.append(result)
        elif result.hash not in seen_hashes:
            seen_hashes.add(result.hash)
            merged.append(result)

    # Add unique Forgetful results
    for result in forgetful_results:
        if result.hash is None:
            merged.append(result)
        elif result.hash not in seen_hashes:
            seen_hashes.add(result.hash)
            merged.append(result)

    return merged[:max_results]


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def test_forgetful_available(
    port: int = 8020,
    force: bool = False,
) -> bool:
    """Check if Forgetful MCP is available with 30s caching.

    Performs TCP health check to Forgetful port.
    Caches result for 30 seconds to minimize overhead.

    Args:
        port: Forgetful server port.
        force: Skip cache and force fresh check.

    Returns:
        True if Forgetful is available.
    """
    now = time.monotonic()
    if not force and _health_cache.last_checked > 0:
        cache_age = now - _health_cache.last_checked
        if cache_age < _health_cache.cache_ttl:
            logger.debug(
                "Using cached Forgetful availability: %s",
                _health_cache.available,
            )
            return _health_cache.available

    available = False
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(float(_config["forgetful_timeout"]))
            result = sock.connect_ex(("localhost", port))
            available = result == 0
        finally:
            sock.close()
    except OSError:
        logger.debug("Forgetful not listening on port %d", port)

    _health_cache.available = available
    _health_cache.last_checked = now

    logger.debug("Forgetful availability: %s (fresh check)", available)
    return available


# Prevent pytest from collecting this production function as a test
setattr(test_forgetful_available, "__test__", False)  # noqa: B010


def get_memory_router_status() -> dict[str, Any]:
    """Return diagnostic information about the Memory Router.

    Returns:
        Dict with Serena, Forgetful, Cache, and Configuration status.
    """
    serena_available = Path(_config["serena_path"]).is_dir()
    forgetful_available = test_forgetful_available()

    if _health_cache.last_checked > 0:
        cache_age = round(time.monotonic() - _health_cache.last_checked, 2)
    else:
        cache_age = -1

    return {
        "Serena": {
            "Available": serena_available,
            "Path": _config["serena_path"],
        },
        "Forgetful": {
            "Available": forgetful_available,
            "Endpoint": f"http://localhost:{_config['forgetful_port']}/mcp",
        },
        "Cache": {
            "AgeSeconds": cache_age,
            "TTLSeconds": _health_cache.cache_ttl,
        },
        "Configuration": dict(_config),
    }


def search_memory(
    query: str,
    max_results: int = 10,
    semantic_only: bool = False,
    lexical_only: bool = False,
) -> list[MemoryResult]:
    """Unified memory search across Serena and Forgetful.

    Main entry point for memory search per ADR-037.
    Routes queries through Serena-first, optionally augments with Forgetful.

    Args:
        query: Search query. Must match pattern ^[a-zA-Z0-9\\s\\-.,_()&:]+$
        max_results: Maximum results to return (1-100).
        semantic_only: Force Forgetful-only search (fails if unavailable).
        lexical_only: Force Serena-only search (skip Forgetful).

    Returns:
        List of MemoryResult objects.

    Raises:
        ValueError: If both semantic_only and lexical_only are True,
            or if query is invalid.
        RuntimeError: If semantic_only and Forgetful is unavailable.
    """
    if semantic_only and lexical_only:
        msg = "Cannot specify both semantic_only and lexical_only"
        raise ValueError(msg)

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

    # Semantic-only mode
    if semantic_only:
        if not test_forgetful_available():
            msg = "Forgetful is not available and semantic_only was specified"
            raise RuntimeError(msg)
        return invoke_forgetful_search(query, max_results=max_results)

    # Lexical-only mode: skip content reading and hashing
    if lexical_only:
        return invoke_serena_search(
            query, max_results=max_results, skip_content=True
        )

    # Augmented mode: check Forgetful availability
    forgetful_available = test_forgetful_available()
    if not forgetful_available:
        logger.debug("Forgetful unavailable, returning Serena-only results")
        return invoke_serena_search(query, max_results=max_results)

    # Both sources available: need content/hashes for dedup
    serena_results = invoke_serena_search(query, max_results=max_results)
    forgetful_results = invoke_forgetful_search(query, max_results=max_results)

    return merge_memory_results(
        serena_results=serena_results,
        forgetful_results=forgetful_results,
        max_results=max_results,
    )


def reset_caches() -> None:
    """Reset all module-level caches (for testing)."""
    global _health_cache, _file_list_cache
    _health_cache = _HealthCache()
    _file_list_cache = _FileListCache()
