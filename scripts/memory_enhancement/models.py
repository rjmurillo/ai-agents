"""Core data models for the memory enhancement layer.

Defines Citation, MemoryLink, VerificationResult, and HealthReport as
frozen (immutable) dataclasses. MemoryWithCitations is mutable to allow
confidence score updates after construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class SourceType(Enum):
    """Classification of citation source targets."""

    FILE = "file"
    FUNCTION = "function"
    ISSUE = "issue"
    PR = "pr"
    ADR = "adr"
    MEMORY = "memory"
    URL = "url"


class CitationStatus(Enum):
    """Verification status of a citation."""

    VALID = "valid"
    STALE = "stale"
    BROKEN = "broken"
    UNVERIFIED = "unverified"


class LinkType(Enum):
    """Relationship type between memories."""

    DEPENDS_ON = "depends_on"
    RELATED_TO = "related_to"
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    REFINES = "refines"


@dataclass(frozen=True)
class Citation:
    """A reference from a memory to an external artifact."""

    source_type: SourceType
    target: str
    context: str
    verified_at: datetime | None = None
    status: CitationStatus = CitationStatus.UNVERIFIED

    def __post_init__(self) -> None:
        """Validate citation invariants."""
        if not self.target:
            raise ValueError("Citation target must be non-empty")
        if self.status != CitationStatus.UNVERIFIED and self.verified_at is None:
            raise ValueError(
                f"Citation with status {self.status.value} must have verified_at set"
            )
        if self.status == CitationStatus.UNVERIFIED and self.verified_at is not None:
            raise ValueError(
                "Citation with status unverified must not have verified_at set"
            )


@dataclass(frozen=True)
class MemoryLink:
    """A typed relationship between two memories."""

    link_type: LinkType
    target_id: str
    context: str

    def __post_init__(self) -> None:
        """Validate link invariants."""
        if not self.target_id:
            raise ValueError("MemoryLink target_id must be non-empty")


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying a single citation."""

    citation: Citation
    is_valid: bool
    reason: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls, citation: Citation, is_valid: bool, reason: str
    ) -> VerificationResult:
        """Create a VerificationResult with the current timestamp."""
        return cls(
            citation=citation,
            is_valid=is_valid,
            reason=reason,
            checked_at=datetime.now(UTC),
        )


@dataclass
class MemoryWithCitations:
    """A memory entry enriched with citations and relationship links."""

    memory_id: str
    title: str
    content: str
    citations: Sequence[Citation] = field(default_factory=list)
    confidence: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tags: Sequence[str] = field(default_factory=list)
    links: Sequence[MemoryLink] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate memory invariants and convert mutable collections to tuples."""
        if not self.memory_id:
            raise ValueError("memory_id must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be between 0.0 and 1.0, got {self.confidence}"
            )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        # Convert mutable lists to tuples for collection immutability
        self.citations = tuple(self.citations)
        self.links = tuple(self.links)
        self.tags = tuple(self.tags)

    def has_stale_citations(self) -> bool:
        """Return True if any citation is stale."""
        return any(c.status == CitationStatus.STALE for c in self.citations)

    def has_broken_citations(self) -> bool:
        """Return True if any citation is broken."""
        return any(c.status == CitationStatus.BROKEN for c in self.citations)

    def citation_validity_ratio(self) -> float:
        """Return the ratio of valid citations to total citations.

        Returns 1.0 when there are no citations.
        """
        if not self.citations:
            return 1.0
        valid_count = sum(1 for c in self.citations if c.status == CitationStatus.VALID)
        return valid_count / len(self.citations)

    def unverified_citations(self) -> list[Citation]:
        """Return citations that have not been verified."""
        return [c for c in self.citations if c.status == CitationStatus.UNVERIFIED]


@dataclass(frozen=True)
class HealthReport:
    """Aggregate health status of the memory system."""

    total_memories: int
    total_citations: int
    valid_citations: int
    stale_citations: int
    broken_citations: int
    unverified_citations: int
    health_score: float
    stale_memories: Sequence[str]
    recommendations: Sequence[str]

    def __post_init__(self) -> None:
        """Validate report invariants and freeze collections."""
        for name in (
            "total_memories",
            "total_citations",
            "valid_citations",
            "stale_citations",
            "broken_citations",
            "unverified_citations",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        citation_sum = (
            self.valid_citations
            + self.stale_citations
            + self.broken_citations
            + self.unverified_citations
        )
        if citation_sum != self.total_citations:
            raise ValueError(
                f"Citation counts must sum to total_citations: "
                f"{citation_sum} != {self.total_citations}"
            )
        if not 0.0 <= self.health_score <= 1.0:
            raise ValueError(
                f"health_score must be between 0.0 and 1.0, got {self.health_score}"
            )
        object.__setattr__(self, "stale_memories", tuple(self.stale_memories))
        object.__setattr__(self, "recommendations", tuple(self.recommendations))
