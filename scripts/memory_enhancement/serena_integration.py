"""Serena memory file parsing and persistence.

Reads and writes .serena/memories/*.md files, extracting metadata
from markdown headers and citation blocks from content.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import frontmatter
import yaml

from .models import (
    Citation,
    LinkType,
    MemoryLink,
    MemoryWithCitations,
    SourceType,
)

_CITATION_PATTERN = re.compile(
    r"\[cite:(?P<source_type>\w+)\]\((?P<target>[^)]+)\)"
    r"(?:\s*-\s*(?P<context>.+))?",
)

_LINK_PATTERN = re.compile(
    r"\[link:(?P<link_type>\w+)\]\((?P<target_id>[^)]+)\)"
    r"(?:\s*-\s*(?P<context>.+))?",
)

_CITATIONS_HEADER_PATTERN = re.compile(r"^##\s+Citations\s*$", re.MULTILINE)
_LINKS_HEADER_PATTERN = re.compile(r"^##\s+Links\s*$", re.MULTILINE)

_TITLE_DATE_PATTERN = re.compile(
    r"^#\s+(?P<title>.+?)\s*\((?P<date>\d{4}-\d{2}-\d{2})\)\s*$",
)


def parse_citation_block(text: str) -> list[Citation]:
    """Extract citations from markdown text using [cite:type](target) syntax.

    Args:
        text: Raw markdown content to parse.

    Returns:
        List of Citation objects found in the text.
    """
    citations: list[Citation] = []
    for match in _CITATION_PATTERN.finditer(text):
        raw_type = match.group("source_type")
        source_type = _parse_source_type(raw_type)
        if source_type is None:
            print(
                f"Warning: unrecognized citation source type '{raw_type}'",
                file=sys.stderr,
            )
            continue
        context = match.group("context") or ""
        citations.append(
            Citation(
                source_type=source_type,
                target=match.group("target"),
                context=context.strip(),
            )
        )
    return citations


def parse_link_block(text: str) -> list[MemoryLink]:
    """Extract memory links from markdown text using [link:type](target) syntax.

    Args:
        text: Raw markdown content to parse.

    Returns:
        List of MemoryLink objects found in the text.
    """
    links: list[MemoryLink] = []
    for match in _LINK_PATTERN.finditer(text):
        raw_type = match.group("link_type")
        link_type = _parse_link_type(raw_type)
        if link_type is None:
            print(
                f"Warning: unrecognized link type '{raw_type}'",
                file=sys.stderr,
            )
            continue
        context = match.group("context") or ""
        links.append(
            MemoryLink(
                link_type=link_type,
                target_id=match.group("target_id"),
                context=context.strip(),
            )
        )
    return links


def load_memory(file_path: Path) -> MemoryWithCitations | None:
    """Load a single memory file and parse its content.

    Supports two formats:
    1. YAML frontmatter with title, tags, created_at, updated_at
    2. Plain markdown with '# Title (YYYY-MM-DD)' header

    Args:
        file_path: Path to a .md memory file.

    Returns:
        Parsed MemoryWithCitations, or None if the file cannot be parsed.
    """
    if not file_path.is_file():
        return None

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Warning: cannot read {file_path}: {exc}", file=sys.stderr)
        return None
    memory_id = file_path.stem

    title, created_at, updated_at, tags, confidence, content = _extract_metadata(
        raw_text
    )
    if title is None:
        title = memory_id

    citations = parse_citation_block(content)
    links = parse_link_block(content)
    content = _strip_citation_link_blocks(content)

    try:
        return MemoryWithCitations(
            memory_id=memory_id,
            title=title,
            content=content,
            citations=citations,
            confidence=confidence,
            created_at=created_at,
            updated_at=updated_at,
            tags=tags,
            links=links,
        )
    except ValueError as exc:
        print(f"Warning: invalid memory data in {file_path}: {exc}", file=sys.stderr)
        return None


def load_memories(memories_dir: Path) -> list[MemoryWithCitations]:
    """Load all memory files from a directory tree.

    Recursively finds all .md files, excluding index files (README.md, CLAUDE.md).

    Args:
        memories_dir: Root directory containing memory .md files.

    Returns:
        List of parsed MemoryWithCitations objects.
    """
    if not memories_dir.is_dir():
        print(
            f"Directory does not exist: {memories_dir.resolve()}",
            file=sys.stderr,
        )
        return []

    skip_names = {"README.md", "CLAUDE.md"}
    memories: list[MemoryWithCitations] = []

    for md_file in sorted(memories_dir.rglob("*.md")):
        if md_file.name in skip_names:
            continue
        memory = load_memory(md_file)
        if memory is not None:
            memories.append(memory)

    if not memories:
        print(
            f"No memory files found in: {memories_dir.resolve()}",
            file=sys.stderr,
        )

    return memories


def save_memory(memory: MemoryWithCitations, memories_dir: Path) -> Path:
    """Persist a memory to disk as a markdown file with YAML frontmatter.

    Args:
        memory: The memory to save.
        memories_dir: Directory to write the file into.

    Returns:
        Path to the written file.
    """
    try:
        memories_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"Cannot create directory {memories_dir}: {exc}") from exc

    file_path = memories_dir / f"{memory.memory_id}.md"

    metadata = {
        "title": memory.title,
        "tags": list(memory.tags),
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
        "confidence": memory.confidence,
    }

    body_parts = [memory.content]
    body_parts.extend(_format_citations(memory.citations))
    body_parts.extend(_format_links(memory.links))

    post = frontmatter.Post(content="\n\n".join(body_parts), **metadata)
    try:
        file_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Cannot write file {file_path}: {exc}") from exc
    return file_path


def _strip_citation_link_blocks(content: str) -> str:
    """Remove ## Citations and ## Links sections from content to prevent duplication.

    When loading a memory that was previously saved, the content may already
    contain these blocks. Stripping them ensures save_memory won't duplicate.

    Also removes inline citation/link markup from body text to prevent duplication
    when citations are stored as structured data.
    """
    lines = content.split("\n")
    result_lines: list[str] = []
    in_block = False

    for line in lines:
        if _CITATIONS_HEADER_PATTERN.match(line) or _LINKS_HEADER_PATTERN.match(line):
            in_block = True
            continue
        if in_block:
            is_new_section = (
                line.startswith("## ")
                and not _CITATIONS_HEADER_PATTERN.match(line)
                and not _LINKS_HEADER_PATTERN.match(line)
            )
            if is_new_section:
                in_block = False
                result_lines.append(line)
            continue
        result_lines.append(line)

    stripped = "\n".join(result_lines).rstrip()
    stripped = _CITATION_PATTERN.sub("", stripped)
    stripped = _LINK_PATTERN.sub("", stripped)
    stripped = re.sub(r"^\s*-\s*$", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped.strip()


def _extract_metadata(
    raw_text: str,
) -> tuple[str | None, datetime, datetime, list[str], float, str]:
    """Extract metadata from raw markdown text.

    Tries YAML frontmatter first, then falls back to title-date header parsing.

    Returns:
        Tuple of (title, created_at, updated_at, tags, confidence, content).
    """
    now = datetime.now(UTC)

    try:
        post = frontmatter.loads(raw_text)
    except yaml.YAMLError:
        # Malformed YAML frontmatter; treat as plain markdown
        print(
            "Warning: malformed YAML frontmatter, treating as plain markdown",
            file=sys.stderr,
        )
        post = frontmatter.Post(content=raw_text)
    has_frontmatter = bool(post.metadata)

    if has_frontmatter:
        title = post.metadata.get("title")
        tags = post.metadata.get("tags", [])
        created_at = _parse_datetime(post.metadata.get("created_at"), now)
        updated_at = _parse_datetime(post.metadata.get("updated_at"), now)
        confidence = _parse_confidence(post.metadata.get("confidence"))
        return title, created_at, updated_at, tags, confidence, post.content

    content = raw_text
    title = None
    created_at = now
    updated_at = now

    first_line = raw_text.split("\n", 1)[0]
    header_match = _TITLE_DATE_PATTERN.match(first_line)
    if header_match:
        title = header_match.group("title")
        date_str = header_match.group("date")
        created_at = _parse_date(date_str, now)
        updated_at = created_at

    return title, created_at, updated_at, [], 0.0, content


def _parse_datetime(value: object, default: datetime) -> datetime:
    """Parse a datetime from a string or return the default.

    Normalizes all parsed datetimes to UTC. If the parsed result is naive
    (no tzinfo), UTC is assumed and attached.

    Handles datetime.date objects from YAML (unquoted dates like 2026-01-01)
    by converting to datetime at midnight UTC.
    """
    if isinstance(value, datetime):
        return _ensure_utc(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        try:
            return _ensure_utc(datetime.fromisoformat(value))
        except ValueError:
            return default
    return default


def _ensure_utc(dt: datetime) -> datetime:
    """Attach UTC to naive datetimes; convert aware datetimes to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_date(date_str: str, default: datetime) -> datetime:
    """Parse a YYYY-MM-DD date string into a timezone-aware datetime."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return default


def _parse_confidence(value: object) -> float:
    """Parse a confidence score from frontmatter, defaulting to 0.0."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _parse_source_type(value: str) -> SourceType | None:
    """Convert a string to SourceType, returning None if invalid."""
    try:
        return SourceType(value.lower())
    except ValueError:
        return None


def _parse_link_type(value: str) -> LinkType | None:
    """Convert a string to LinkType, returning None if invalid."""
    try:
        return LinkType(value.lower())
    except ValueError:
        return None


def _format_citations(citations: Sequence[Citation]) -> list[str]:
    """Format citations as markdown citation blocks."""
    if not citations:
        return []
    lines = ["## Citations"]
    for c in citations:
        line = f"[cite:{c.source_type.value}]({c.target})"
        if c.context:
            line += f" - {c.context}"
        lines.append(line)
    return ["\n".join(lines)]


def _format_links(links: Sequence[MemoryLink]) -> list[str]:
    """Format memory links as markdown link blocks."""
    if not links:
        return []
    lines = ["## Links"]
    for link in links:
        line = f"[link:{link.link_type.value}]({link.target_id})"
        if link.context:
            line += f" - {link.context}"
        lines.append(line)
    return ["\n".join(lines)]
