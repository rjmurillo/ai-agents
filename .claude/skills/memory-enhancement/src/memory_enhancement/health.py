"""Health reporting for Serena memories.

Batch health checks across all memories with staleness detection,
exemption support, and structured reporting for CI integration.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import yaml

from .citations import VerificationResult, verify_memory
from .models import Memory


class HealthStatus(Enum):
    """Health status for a single memory."""

    HEALTHY = "healthy"
    STALE = "stale"
    EXEMPT = "exempt"
    ERROR = "error"


@dataclass
class MemoryHealthEntry:
    """Health check result for a single memory."""

    memory_id: str
    status: HealthStatus
    citation_count: int = 0
    valid_count: int = 0
    confidence: float = 0.5
    stale_citations: list[dict[str, object]] = field(default_factory=list)
    error_message: str | None = None


@dataclass
class HealthReport:
    """Aggregate health report across all memories."""

    entries: list[MemoryHealthEntry] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total(self) -> int:
        """Total number of memories checked."""
        return len(self.entries)

    @property
    def healthy_count(self) -> int:
        """Number of healthy memories."""
        return sum(1 for e in self.entries if e.status == HealthStatus.HEALTHY)

    @property
    def stale_count(self) -> int:
        """Number of stale memories."""
        return sum(1 for e in self.entries if e.status == HealthStatus.STALE)

    @property
    def exempt_count(self) -> int:
        """Number of exempt memories."""
        return sum(1 for e in self.entries if e.status == HealthStatus.EXEMPT)

    @property
    def error_count(self) -> int:
        """Number of memories that failed to check."""
        return sum(1 for e in self.entries if e.status == HealthStatus.ERROR)

    @property
    def has_stale(self) -> bool:
        """Whether any memories are stale."""
        return self.stale_count > 0

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "checked_at": self.checked_at.isoformat(),
            "summary": {
                "total": self.total,
                "healthy": self.healthy_count,
                "stale": self.stale_count,
                "exempt": self.exempt_count,
                "errors": self.error_count,
            },
            "entries": [
                {
                    "memory_id": e.memory_id,
                    "status": e.status.value,
                    "citation_count": e.citation_count,
                    "valid_count": e.valid_count,
                    "confidence": round(e.confidence, 2),
                    "stale_citations": e.stale_citations,
                    "error_message": e.error_message,
                }
                for e in self.entries
            ],
        }

    def to_markdown(self) -> str:
        """Generate a Markdown health report for PR comments."""
        lines: list[str] = []
        lines.append("## Memory Health Report")
        lines.append("")

        if self.total == 0:
            lines.append("No memories with citations found.")
            return "\n".join(lines)

        status_icon = "[PASS]" if not self.has_stale else "[WARN]"
        lines.append(
            f"**{status_icon}** {self.healthy_count + self.exempt_count}/{self.total} "
            f"memories healthy"
        )
        lines.append("")

        lines.append("| Memory | Status | Citations | Confidence |")
        lines.append("|--------|--------|-----------|------------|")

        for entry in self.entries:
            icon = _status_icon(entry.status)
            lines.append(
                f"| {entry.memory_id} | {icon} {entry.status.value} "
                f"| {entry.valid_count}/{entry.citation_count} "
                f"| {entry.confidence:.0%} |"
            )

        lines.append("")
        lines.append(
            f"**Summary**: {self.healthy_count} healthy, "
            f"{self.stale_count} stale, "
            f"{self.exempt_count} exempt, "
            f"{self.error_count} errors"
        )

        if self.stale_count > 0:
            lines.append("")
            lines.append("### Stale Citations")
            lines.append("")
            for entry in self.entries:
                if entry.status != HealthStatus.STALE:
                    continue
                lines.append(f"**{entry.memory_id}**:")
                for sc in entry.stale_citations:
                    loc = sc.get("path", "unknown")
                    if sc.get("line"):
                        loc += f":{sc['line']}"
                    reason = sc.get("mismatch_reason", "unknown")
                    lines.append(f"- `{loc}` - {reason}")
                lines.append("")

        return "\n".join(lines)


def _status_icon(status: HealthStatus) -> str:
    """Return a text indicator for a health status."""
    icons = {
        HealthStatus.HEALTHY: "[PASS]",
        HealthStatus.STALE: "[FAIL]",
        HealthStatus.EXEMPT: "[SKIP]",
        HealthStatus.ERROR: "[ERR]",
    }
    return icons.get(status, "[?]")


def check_memory_health(memory: Memory, repo_root: Path) -> MemoryHealthEntry:
    """Check health of a single memory.

    If the memory is marked exempt, returns EXEMPT status without verification.
    Otherwise, runs citation verification and returns HEALTHY or STALE.
    """
    if memory.exempt:
        return MemoryHealthEntry(
            memory_id=memory.id,
            status=HealthStatus.EXEMPT,
            citation_count=len(memory.citations),
            valid_count=len(memory.citations),
            confidence=memory.confidence,
        )

    if not memory.citations:
        return MemoryHealthEntry(
            memory_id=memory.id,
            status=HealthStatus.HEALTHY,
            citation_count=0,
            valid_count=0,
            confidence=memory.confidence,
        )

    result: VerificationResult = verify_memory(memory, repo_root)

    stale_details = [
        {
            "path": c.path,
            "line": c.line,
            "snippet": c.snippet,
            "mismatch_reason": c.mismatch_reason,
        }
        for c in result.stale_citations
    ]

    status = HealthStatus.HEALTHY if result.valid else HealthStatus.STALE

    return MemoryHealthEntry(
        memory_id=result.memory_id,
        status=status,
        citation_count=result.total_citations,
        valid_count=result.valid_count,
        confidence=result.confidence,
        stale_citations=stale_details,
    )


def check_all_health(
    memories_dir: Path, repo_root: Path
) -> HealthReport:
    """Run health checks on all memories in a directory.

    Parses each .md file, checks health, and returns an aggregate report.
    Files that fail to parse are recorded as ERROR entries.
    """
    report = HealthReport()

    if not memories_dir.exists():
        return report

    for path in sorted(memories_dir.glob("*.md")):
        try:
            memory = Memory.from_file(path)
        except (
            yaml.YAMLError, UnicodeDecodeError, OSError,
            KeyError, ValueError, AttributeError, TypeError,
        ) as e:
            report.entries.append(
                MemoryHealthEntry(
                    memory_id=path.stem,
                    status=HealthStatus.ERROR,
                    error_message=f"{type(e).__name__}: {e}",
                )
            )
            continue

        entry = check_memory_health(memory, repo_root)
        report.entries.append(entry)

    return report
