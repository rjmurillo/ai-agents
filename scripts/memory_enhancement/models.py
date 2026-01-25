"""Data models for memory enhancement layer.

Dataclasses for Memory, Citation, and Link per PRD section 4.5.1.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import frontmatter


class LinkType(Enum):
    """Typed relationship between memories."""
    RELATED = "related"
    SUPERSEDES = "supersedes"
    BLOCKS = "blocks"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"


@dataclass
class Citation:
    """Code reference with verification metadata."""
    path: str
    line: Optional[int] = None
    snippet: Optional[str] = None
    verified: Optional[datetime] = None
    valid: Optional[bool] = None
    mismatch_reason: Optional[str] = None


@dataclass
class Link:
    """Typed relationship to another memory."""
    link_type: LinkType
    target_id: str


@dataclass
class Memory:
    """Serena memory with citations and links."""
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
        """Parse a Serena memory markdown file."""
        post = frontmatter.load(path)
        meta = post.metadata

        citations = [
            Citation(
                path=c.get("path", ""),
                line=c.get("line"),
                snippet=c.get("snippet"),
            )
            for c in meta.get("citations", [])
        ]

        links = []
        for link_data in meta.get("links", []):
            try:
                link_type = LinkType(link_data.get("type", "related"))
                links.append(Link(link_type=link_type, target_id=link_data.get("target", "")))
            except ValueError:
                pass  # Skip invalid link types

        return cls(
            id=meta.get("id", path.stem),
            subject=meta.get("subject", path.stem),
            path=path,
            content=post.content,
            citations=citations,
            links=links,
            tags=meta.get("tags", []),
            confidence=float(meta.get("confidence", 1.0)),
            last_verified=cls._parse_date(meta.get("last_verified")),
        )

    @staticmethod
    def _parse_date(value) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def get_links_by_type(self, link_type: LinkType) -> list[str]:
        """Return target IDs for links of the given type."""
        return [link.target_id for link in self.links if link.link_type == link_type]
