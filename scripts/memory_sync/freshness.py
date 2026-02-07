"""Freshness validation for Serena-Forgetful memory drift.

Compares the state of .serena/memories/ files against the sync
state file to detect in-sync, stale, missing, and orphaned entries.

See: ADR-037, Issue #747
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from scripts.memory_sync.models import FreshnessDetail, FreshnessReport, FreshnessStatus
from scripts.memory_sync.sync_engine import compute_content_hash, load_state

_logger = logging.getLogger(__name__)


def check_freshness(
    project_root: Path,
    memories_dir: Path | None = None,
) -> FreshnessReport:
    """Generate a freshness report comparing Serena memories to sync state.

    Args:
        project_root: Absolute path to the project root.
        memories_dir: Override for the memories directory.
            Defaults to ``project_root / ".serena" / "memories"``.

    Returns:
        FreshnessReport with counts and details for each memory.
    """
    start = time.monotonic()
    mem_dir = memories_dir or (project_root / ".serena" / "memories")
    state = load_state(project_root)

    details: list[FreshnessDetail] = []
    serena_names: set[str] = set()

    if mem_dir.is_dir():
        for md_file in sorted(mem_dir.glob("*.md")):
            name = md_file.stem
            serena_names.add(name)
            content = md_file.read_text("utf-8")
            serena_hash = compute_content_hash(content)

            existing = state.get(name)
            if existing is None:
                details.append(FreshnessDetail(
                    name=name,
                    status=FreshnessStatus.MISSING,
                    serena_hash=serena_hash,
                ))
            elif existing.get("hash") == serena_hash:
                details.append(FreshnessDetail(
                    name=name,
                    status=FreshnessStatus.IN_SYNC,
                    serena_hash=serena_hash,
                    forgetful_hash=existing.get("hash"),
                    forgetful_id=existing.get("forgetful_id"),
                ))
            else:
                details.append(FreshnessDetail(
                    name=name,
                    status=FreshnessStatus.STALE,
                    serena_hash=serena_hash,
                    forgetful_hash=existing.get("hash"),
                    forgetful_id=existing.get("forgetful_id"),
                ))

    # Check for orphaned entries (in state but not in Serena)
    for name, entry in state.items():
        if name not in serena_names:
            details.append(FreshnessDetail(
                name=name,
                status=FreshnessStatus.ORPHANED,
                forgetful_hash=entry.get("hash"),
                forgetful_id=entry.get("forgetful_id"),
            ))

    in_sync = sum(1 for d in details if d.status == FreshnessStatus.IN_SYNC)
    stale = sum(1 for d in details if d.status == FreshnessStatus.STALE)
    missing = sum(1 for d in details if d.status == FreshnessStatus.MISSING)
    orphaned = sum(1 for d in details if d.status == FreshnessStatus.ORPHANED)

    duration_ms = (time.monotonic() - start) * 1000

    return FreshnessReport(
        total=len(details),
        in_sync=in_sync,
        stale=stale,
        missing=missing,
        orphaned=orphaned,
        details=details,
        duration_ms=duration_ms,
    )
