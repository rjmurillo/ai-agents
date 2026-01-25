"""Data models for memory enhancement layer."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class LinkType(Enum):
    """Typed relationship between memories."""

    RELATED = "related"  # Bidirectional discovery
    SUPERSEDES = "supersedes"  # Deprecation chain
    BLOCKS = "blocks"  # Dependency ordering
    IMPLEMENTS = "implements"  # ADR traceability
    EXTENDS = "extends"  # Inheritance chain


@dataclass
class Citation:
    """Reference to a specific code location."""

    path: str
    line: Optional[int] = None
    snippet: Optional[str] = None
    verified: Optional[datetime] = None
    valid: Optional[bool] = None
    mismatch_reason: Optional[str] = None


@dataclass
class Link:
    """Typed edge in the memory graph."""

    link_type: LinkType
    target_id: str


@dataclass
class GraphEdge:
    """Edge in the memory graph with type information."""

    source_id: str
    target_id: str
    link_type: LinkType


@dataclass
class GraphResult:
    """Result of graph traversal with typed edges."""

    nodes: dict[str, list[Link]]  # node -> outgoing typed links
    edges: list["GraphEdge"] = field(default_factory=list)
    visited_count: int = 0
    max_depth_reached: int = 0


@dataclass
class Memory:
    """Parsed Serena memory with citations and typed links."""

    id: str
    subject: str
    path: Path
    content: str
    citations: list[Citation] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    last_verified: Optional[datetime] = None

    @classmethod
    def from_serena_file(cls, path: Path) -> "Memory":
        """
        Parse a Serena memory markdown file with YAML frontmatter.

        Args:
            path: Path to the memory file

        Returns:
            Memory object with parsed frontmatter and content
        """
        try:
            import frontmatter
        except ImportError:
            # Fallback: Parse manually if python-frontmatter not installed
            return cls._parse_manual(path)

        post = frontmatter.load(path)

        # Extract ID from frontmatter or fall back to filename
        memory_id = post.metadata.get("id", path.stem)
        subject = post.metadata.get("subject", "")

        # Extract citations from frontmatter
        citations = [
            Citation(
                path=c.get("path", ""),
                line=c.get("line"),
                snippet=c.get("snippet"),
                verified=cls._parse_date(c.get("verified")),
            )
            for c in post.metadata.get("citations", [])
        ]

        # Extract typed links from frontmatter
        links = []
        for link_entry in post.metadata.get("links", []):
            # Each entry is a dict like {"related": "mem-foo-001"}
            for link_type_str, target_id in link_entry.items():
                try:
                    link_type = LinkType(link_type_str)
                    links.append(Link(link_type=link_type, target_id=target_id))
                except ValueError:
                    pass  # Unknown link type, skip

        # Extract tags
        tags = post.metadata.get("tags", [])

        # Extract confidence and last_verified
        confidence = post.metadata.get("confidence", 0.5)
        last_verified = cls._parse_date(post.metadata.get("last_verified"))

        return cls(
            id=memory_id,
            subject=subject,
            path=path,
            content=post.content,
            citations=citations,
            links=links,
            tags=tags,
            confidence=confidence,
            last_verified=last_verified,
        )

    @classmethod
    def _parse_manual(cls, path: Path) -> "Memory":
        """
        Fallback parser for files without frontmatter support.

        Args:
            path: Path to the memory file

        Returns:
            Memory object with minimal metadata (no frontmatter parsing)
        """
        content = path.read_text()
        return cls(
            id=path.stem,
            subject="",
            path=path,
            content=content,
            citations=[],
            links=[],
            tags=[],
            confidence=0.5,
            last_verified=None,
        )

    def get_links_by_type(self, link_type: LinkType) -> list[str]:
        """
        Get all target IDs for a specific link type.

        Args:
            link_type: The type of link to filter by

        Returns:
            List of target memory IDs
        """
        return [link.target_id for link in self.links if link.link_type == link_type]

    @staticmethod
    def _parse_date(value) -> Optional[datetime]:
        """
        Parse date from string or datetime.

        Args:
            value: Date value (string, datetime, or None)

        Returns:
            Parsed datetime or None
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None
