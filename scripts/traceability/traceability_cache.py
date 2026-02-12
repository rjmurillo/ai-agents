"""Caching module for traceability graph operations.

Provides file-based caching for parsed spec data with automatic invalidation
based on file modification times. Optimizes performance by avoiding repeated
YAML parsing of unchanged spec files.

Cache Strategy:
- Per-file caching with modification time tracking
- Automatic invalidation on file changes
- In-memory cache for current session
- Disk-based cache (.agents/.cache/traceability/) for cross-session persistence

Performance Targets:
- First run: Full parse (baseline)
- Subsequent runs (no changes): <100ms for 100 specs
- Partial changes: Only re-parse changed files
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_memory_cache: dict[str, dict[str, Any]] = {}

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".agents" / ".cache" / "traceability"


def initialize_cache() -> None:
    """Create the cache directory structure if it does not exist."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_key(file_path: str | Path) -> str:
    """Generate a cache key from a file path."""
    relative = str(file_path).replace(str(Path.cwd()), "")
    return re.sub(r'[\\/:*?"<>|]', "_", relative)


def get_file_hash(file_path: str | Path) -> str | None:
    """Get a fast hash of file metadata for cache validation.

    Uses mtime + size as a fast change detector instead of content hashing.
    """
    p = Path(file_path)
    if not p.exists():
        return None
    stat = p.stat()
    return f"{int(stat.st_mtime * 10_000_000)}_{stat.st_size}"


def get_cached_spec(
    file_path: str | Path, current_hash: str
) -> dict[str, Any] | None:
    """Retrieve a cached spec if valid, otherwise return None."""
    cache_key = get_cache_key(file_path)

    if cache_key in _memory_cache:
        cached = _memory_cache[cache_key]
        if cached["hash"] == current_hash:
            return cached["spec"]

    cache_file = _CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached["hash"] == current_hash:
                spec = {
                    "type": cached.get("type", ""),
                    "id": cached.get("id", ""),
                    "status": cached.get("status", ""),
                    "related": list(cached.get("related", [])),
                    "filePath": str(file_path),
                }
                _memory_cache[cache_key] = {"hash": current_hash, "spec": spec}
                return spec
        except (json.JSONDecodeError, KeyError):
            pass

    return None


def set_cached_spec(
    file_path: str | Path, file_hash: str, spec: dict[str, Any]
) -> None:
    """Cache a parsed spec to both memory and disk."""
    initialize_cache()
    cache_key = get_cache_key(file_path)

    _memory_cache[cache_key] = {"hash": file_hash, "spec": spec}

    cache_file = _CACHE_DIR / f"{cache_key}.json"
    cache_data = {
        "hash": file_hash,
        "type": spec.get("type", ""),
        "id": spec.get("id", ""),
        "status": spec.get("status", ""),
        "related": spec.get("related", []),
    }

    try:
        cache_file.write_text(
            json.dumps(cache_data, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def clear_cache() -> None:
    """Clear all cached data (memory and disk)."""
    _memory_cache.clear()

    if _CACHE_DIR.exists():
        for f in _CACHE_DIR.glob("*.json"):
            try:
                f.unlink()
            except OSError:
                pass


def get_cache_stats() -> dict[str, Any]:
    """Return cache statistics for monitoring and debugging."""
    disk_count = 0
    if _CACHE_DIR.exists():
        disk_count = sum(1 for _ in _CACHE_DIR.glob("*.json"))

    return {
        "memory_cache_entries": len(_memory_cache),
        "disk_cache_entries": disk_count,
        "cache_directory": str(_CACHE_DIR),
    }
