"""Data models for memory synchronization.

Defines SyncOperation, SyncResult, and FreshnessReport used
across the sync engine and CLI.

See: ADR-037, Issue #747
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SyncOperation(Enum):
    """Type of sync operation to perform."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SKIP = "skip"


class FreshnessStatus(Enum):
    """Status of a single memory in the freshness check."""

    IN_SYNC = "in_sync"
    STALE = "stale"
    MISSING = "missing"
    ORPHANED = "orphaned"


@dataclass
class SyncResult:
    """Result of a single memory sync operation."""

    path: Path
    operation: SyncOperation
    success: bool
    error: str | None = None
    forgetful_id: str | None = None
    duration_ms: float = 0.0


@dataclass
class FreshnessDetail:
    """Detail for a single memory in the freshness report."""

    name: str
    status: FreshnessStatus
    serena_hash: str | None = None
    forgetful_hash: str | None = None
    forgetful_id: str | None = None


@dataclass
class FreshnessReport:
    """Summary of memory freshness across Serena and Forgetful."""

    total: int = 0
    in_sync: int = 0
    stale: int = 0
    missing: int = 0
    orphaned: int = 0
    details: list[FreshnessDetail] = field(default_factory=list)
    duration_ms: float = 0.0
