"""Index and detail-file formatting primitives for context outputs."""

from __future__ import annotations

import re
from pathlib import Path

from context_output_parsing import Section, _update_fence_marker


def summarize_section(section: Section) -> str:
    """Produce a one-line summary of a section for the index."""
    fence_marker: str | None = None
    for line in section.content.split("\n"):
        stripped = line.strip()
        fence_line, fence_marker = _update_fence_marker(stripped, fence_marker)
        if fence_line or fence_marker or not stripped:
            continue
        if re.match(r"^#{1,6}\s+|^[-|#>].{0,2}$", stripped):
            continue
        if re.match(r"^\|[-:\s|]+\|$", stripped):
            continue
        summary = stripped.lstrip("-*> ").rstrip()
        if len(summary) > 80:
            summary = summary[:77] + "..."
        return summary
    return "(see detail file)"


def build_index(sections: list[Section], detail_dir: str) -> str:
    """Build a pipe-delimited index referencing detail files."""
    lines: list[str] = []
    for section, slug in _named_sections(sections):
        if section.heading == "preamble" and not section.content:
            continue
        heading_display = "Overview" if section.heading == "preamble" else section.heading
        lines.append(f"[{heading_display}]")
        summary = summarize_section(section)
        detail_path = (Path(detail_dir) / f"{slug}.md").as_posix()
        lines.append(f"|{summary} (see: {detail_path})")
    return "\n".join(lines)


def _named_sections(sections: list[Section]) -> list[tuple[Section, str]]:
    """Assign stable, unique detail-file slugs to parsed sections."""
    used_slugs: set[str] = set()
    named_sections: list[tuple[Section, str]] = []
    for section in sections:
        base_slug = section.slug
        slug = base_slug
        suffix = 0
        while slug in used_slugs:
            suffix += 1
            slug = f"{base_slug}-{suffix}"
        used_slugs.add(slug)
        named_sections.append((section, slug))
    return named_sections


def _detail_file_contents(sections: list[Section]) -> dict[str, str]:
    """Build the detail-file contents without touching the filesystem."""
    return {
        f"{slug}.md": (
            f"{'#' * max(section.level, 1)} {section.heading}\n"
            + (f"\n{section.content.rstrip()}\n" if section.content.rstrip() else "")
        )
        for section, slug in _named_sections(sections)
    }
