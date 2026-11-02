"""Markdown parsing primitives for context output extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Section:
    """A parsed markdown section."""

    heading: str
    level: int
    content: str
    slug: str


def slugify(heading: str) -> str:
    """Convert a heading to a filesystem-safe slug."""
    slug = heading.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug or "untitled"


def _update_fence_marker(line: str, current: str | None) -> tuple[bool, str | None]:
    """Track a fenced-code delimiter and report whether the line was one."""
    match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
    if not match:
        return False, current
    marker = match.group(1)
    if current is None:
        return True, marker
    if marker[0] == current[0] and len(marker) >= len(current):
        return True, None
    return True, current


def parse_sections(content: str) -> list[Section]:
    """Parse markdown content into sections split by headings."""
    lines = content.split("\n")
    sections: list[Section] = []
    current_heading = "preamble"
    current_level = 0
    current_lines: list[str] = []
    fence_marker: str | None = None

    for line in lines:
        fence_line, fence_marker = _update_fence_marker(line, fence_marker)
        if fence_line:
            current_lines.append(line)
            continue

        match = None if fence_marker else re.match(r"^(#{1,2})\s+(.+)$", line)
        if match:
            body = "\n".join(current_lines).strip()
            if body or current_heading != "preamble":
                sections.append(
                    Section(
                        heading=current_heading,
                        level=current_level,
                        content=body,
                        slug=slugify(current_heading),
                    )
                )
            current_heading = match.group(2).strip()
            current_level = len(match.group(1))
            current_lines = []
        else:
            current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body or current_heading != "preamble":
        sections.append(
            Section(
                heading=current_heading,
                level=current_level,
                content=body,
                slug=slugify(current_heading),
            )
        )

    return sections
