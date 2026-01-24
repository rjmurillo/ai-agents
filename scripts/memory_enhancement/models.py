"""Data models for memory enhancement layer.

This module provides data structures for representing memories, citations,
and links between memories following the Serena memory schema.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import frontmatter


class LinkType(Enum):
    """Types of relationships between memories."""

    RELATED = "RELATED"
    SUPERSEDES = "SUPERSEDES"
    BLOCKS = "BLOCKS"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"


@dataclass
class Citation:
    """Reference to a specific location in the codebase.

    Attributes:
        path: Relative file path from repository root
        line: Line number (1-indexed), None for file-level citations
        snippet: Optional code snippet for fuzzy matching
        verified: Timestamp of last verification
        valid: Whether the citation is still valid
        mismatch_reason: Details on why validation failed
    """

    path: str
    line: Optional[int] = None
    snippet: Optional[str] = None
    verified: Optional[datetime] = None
    valid: Optional[bool] = None
    mismatch_reason: Optional[str] = None


@dataclass
class Link:
    """Typed relationship to another memory.

    Attributes:
        link_type: Type of relationship (RELATED, SUPERSEDES, etc.)
        target_id: ID of the target memory
    """

    link_type: LinkType
    target_id: str


@dataclass
class Memory:
    """Representation of a Serena memory with citations and links.

    Attributes:
        id: Unique memory identifier
        subject: Memory title/subject
        path: File path to memory markdown file
        content: Markdown body content
        citations: List of code references
        links: Relationships to other memories
        tags: Classification tags
        confidence: Trust score (0.0-1.0)
        last_verified: Timestamp of last citation verification
    """

    id: str
    subject: str
    path: Path
    content: str
    citations: list[Citation] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    confidence: float = 1.0
    last_verified: Optional[datetime] = None

    @classmethod
    def from_serena_file(cls, path: Path) -> "Memory":
        """Parse a Serena memory file with YAML frontmatter.

        Args:
            path: Path to the memory markdown file

        Returns:
            Memory instance populated from file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file has invalid structure
        """
        if not path.exists():
            raise FileNotFoundError(f"Memory file not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            post = frontmatter.load(f)

        metadata = post.metadata
        content = post.content

        # Extract memory ID from metadata or filename
        memory_id = metadata.get("id", path.stem)
        subject = metadata.get("subject", "")

        # Parse citations
        citations_raw = metadata.get("citations", [])
        citations = [
            Citation(
                path=c["path"],
                line=c.get("line"),
                snippet=c.get("snippet"),
                verified=cls._parse_date(c.get("verified")),
                valid=c.get("valid"),
                mismatch_reason=c.get("mismatch_reason"),
            )
            for c in citations_raw
        ]

        # Parse links
        links_raw = metadata.get("links", [])
        links = []
        for link_data in links_raw:
            try:
                link_type = LinkType(link_data.get("link_type", "RELATED"))
                links.append(Link(link_type=link_type, target_id=link_data["target_id"]))
            except (ValueError, KeyError):
                # Skip invalid links but don't fail parsing
                continue

        # Extract other metadata
        tags = metadata.get("tags", [])
        confidence = float(metadata.get("confidence", 1.0))
        last_verified = cls._parse_date(metadata.get("last_verified"))

        return cls(
            id=memory_id,
            subject=subject,
            path=path,
            content=content,
            citations=citations,
            links=links,
            tags=tags,
            confidence=confidence,
            last_verified=last_verified,
        )

    def get_links_by_type(self, link_type: LinkType) -> list[str]:
        """Filter links by type and return target IDs.

        Args:
            link_type: Type of relationship to filter by

        Returns:
            List of target memory IDs
        """
        return [link.target_id for link in self.links if link.link_type == link_type]

    @staticmethod
    def _parse_date(value) -> Optional[datetime]:
        """Parse date from various formats.

        Args:
            value: Date value (None, datetime, or ISO string)

        Returns:
            datetime instance or None
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return None
