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
    RELATED = "RELATED"
    SUPERSEDES = "SUPERSEDES"
    BLOCKS = "BLOCKS"
    IMPLEMENTS = "IMPLEMENTS"
    EXTENDS = "EXTENDS"


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
                # Support both 'link_type' and 'type' field names for compatibility
                type_value = link_data.get("link_type") or link_data.get("type")
                if type_value is None:
                    continue  # Skip links without a type
                link_type = LinkType(type_value)
                # Support both 'target_id' and 'target' field names for compatibility
                target = link_data.get("target_id") or link_data.get("target", "")
                if target:  # Only add links with non-empty targets
                    links.append(Link(link_type=link_type, target_id=target))
            except ValueError:
                pass  # Skip invalid link types

        return cls(
            id=meta.get("id", path.stem),
            subject=meta.get("subject", ""),
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
