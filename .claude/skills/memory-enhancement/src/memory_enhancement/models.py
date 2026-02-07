"""Core data models for memory enhancement.

Defines Citation, Link, and Memory dataclasses that map
to the YAML frontmatter schema in Serena memory files.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path

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
    """Reference to a specific code location."""

    path: str
    line: int | None = None
    snippet: str | None = None
    verified: datetime | None = None
    valid: bool | None = None
    mismatch_reason: str | None = None


@dataclass
class Link:
    """Typed relationship between two memories."""

    link_type: LinkType
    target_id: str


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
    last_verified: datetime | None = None

    @classmethod
    def from_file(cls, path: Path) -> "Memory":
        """Parse a Serena memory markdown file with YAML frontmatter."""
        post = frontmatter.load(str(path))

        memory_id = post.metadata.get("id", path.stem)
        subject = post.metadata.get("subject", "")

        citations = [
            Citation(
                path=c.get("path", ""),
                line=c.get("line"),
                snippet=c.get("snippet"),
                verified=_parse_date(c.get("verified")),
            )
            for c in post.metadata.get("citations", [])
        ]

        links = []
        for link_entry in post.metadata.get("links", []):
            for link_type_str, target_id in link_entry.items():
                try:
                    link_type = LinkType(link_type_str)
                    links.append(Link(link_type=link_type, target_id=target_id))
                except ValueError:
                    _logger.warning(
                        "Unknown link type '%s' in %s, skipping",
                        link_type_str,
                        path,
                    )

        tags = post.metadata.get("tags", [])
        confidence = post.metadata.get("confidence", 0.5)
        last_verified = _parse_date(post.metadata.get("last_verified"))

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

    def get_links_by_type(self, link_type: LinkType) -> list[str]:
        """Get all target IDs for a specific link type."""
        return [link.target_id for link in self.links if link.link_type == link_type]


_logger = logging.getLogger(__name__)


def _parse_date(value: object) -> datetime | None:
    """Parse a date value.

    Accepts None, datetime, date, or ISO-format string.
    Returns None for unsupported types or malformed strings.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            _logger.warning("Cannot parse date string: '%s'", value)
            return None
    return None
