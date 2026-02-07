"""Freshness validation for Serena-Forgetful memory drift.

Compares the state of .serena/memories/ files against the sync
state file to detect in-sync, stale, missing, and orphaned entries.

See: ADR-037, Issue #747
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from scripts.memory_sync.models import FreshnessDetail, FreshnessReport, FreshnessStatus
from scripts.memory_sync.sync_engine import compute_content_hash, load_state

_logger = logging.getLogger(__name__)


def check_freshness(
    project_root: Path,
    memories_dir: Path | None = None,
) -> FreshnessReport:
    """Generate a freshness report comparing Serena memories to sync state."""
    start = time.monotonic()
    mem_dir = memories_dir or (project_root / ".serena" / "memories")
    state = load_state(project_root)

    details, serena_names = _classify_memory_files(mem_dir, state)
    details.extend(_find_orphaned(state, serena_names))

    counts = _count_statuses(details)
    return FreshnessReport(
        **counts,
        details=details,
        duration_ms=(time.monotonic() - start) * 1000,
    )


def _classify_memory_files(
    mem_dir: Path, state: dict[str, Any]
) -> tuple[list[FreshnessDetail], set[str]]:
    """Classify each Serena memory file as MISSING, IN_SYNC, or STALE."""
    details: list[FreshnessDetail] = []
    serena_names: set[str] = set()
    if not mem_dir.is_dir():
        return details, serena_names

    for md_file in sorted(mem_dir.glob("*.md")):
        name = md_file.stem
        serena_names.add(name)
        serena_hash = compute_content_hash(md_file.read_text("utf-8"))
        existing = state.get(name)
        details.append(_classify_one(name, serena_hash, existing))
    return details, serena_names


def _classify_one(
    name: str, serena_hash: str, existing: dict[str, Any] | None
) -> FreshnessDetail:
    """Classify a single memory against its sync state entry."""
    if existing is None:
        return FreshnessDetail(
            name=name, status=FreshnessStatus.MISSING, serena_hash=serena_hash,
        )
    in_sync = existing.get("hash") == serena_hash
    status = FreshnessStatus.IN_SYNC if in_sync else FreshnessStatus.STALE
    return FreshnessDetail(
        name=name,
        status=status,
        serena_hash=serena_hash,
        forgetful_hash=existing.get("hash"),
        forgetful_id=existing.get("forgetful_id"),
    )


def _find_orphaned(state: dict[str, Any], serena_names: set[str]) -> list[FreshnessDetail]:
    """Find state entries with no corresponding Serena file."""
    return [
        FreshnessDetail(
            name=name,
            status=FreshnessStatus.ORPHANED,
            forgetful_hash=entry.get("hash"),
            forgetful_id=entry.get("forgetful_id"),
        )
        for name, entry in state.items()
        if name not in serena_names
    ]


def _count_statuses(details: list[FreshnessDetail]) -> dict[str, int]:
    """Count details by status, returning a dict suitable for FreshnessReport."""
    return {
        "total": len(details),
        "in_sync": sum(1 for d in details if d.status == FreshnessStatus.IN_SYNC),
        "stale": sum(1 for d in details if d.status == FreshnessStatus.STALE),
        "missing": sum(1 for d in details if d.status == FreshnessStatus.MISSING),
        "orphaned": sum(1 for d in details if d.status == FreshnessStatus.ORPHANED),
    }
