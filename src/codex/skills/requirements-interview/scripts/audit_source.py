"""Source-document anchoring for the requirements-interview audit mode.

A source anchor names a section plus an exact quote or a line range. This module
parses Markdown sections and proves an anchor points at real text, so a question
can never cite a phrase the document does not contain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


class AnchorError(ValueError):
    """An anchor does not resolve against the source document."""


@dataclass(frozen=True)
class Section:
    heading: str
    level: int
    start: int  # 1-based line of the heading
    end: int  # 1-based last line of the section body


def normalize(text: str) -> str:
    """Collapse whitespace so line wrapping never hides a quote."""

    return " ".join(text.split())


def parse_sections(lines: list[str]) -> list[Section]:
    """Return every Markdown heading section, ignoring fenced code blocks."""

    found: list[tuple[str, int, int]] = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else _HEADING_RE.match(line)
        if match:
            found.append((normalize(match.group(2)), len(match.group(1)), number))
    return [_close_section(found, index, len(lines)) for index in range(len(found))]


def _close_section(found: list[tuple[str, int, int]], index: int, total: int) -> Section:
    heading, level, start = found[index]
    end = total
    for _, next_level, next_start in found[index + 1 :]:
        if next_level <= level:
            end = next_start - 1
            break
    return Section(heading=heading, level=level, start=start, end=end)


def find_section(sections: list[Section], name: str) -> Section:
    """Resolve a section by its heading, or by a leading number such as ``3.2``."""

    wanted = normalize(name)
    exact = [s for s in sections if s.heading == wanted]
    matches = exact or [s for s in sections if s.heading.startswith(wanted + " ")]
    if not matches:
        raise AnchorError(f"section {name!r} not found")
    if len(matches) > 1:
        raise AnchorError(f"section {name!r} is ambiguous ({len(matches)} headings match)")
    return matches[0]


def section_body(lines: list[str], section: Section) -> str:
    return "\n".join(lines[section.start - 1 : section.end])


def _line_range(raw: Any, section: Section, total: int) -> tuple[int, int]:
    ok = isinstance(raw, list) and len(raw) == 2 and all(type(n) is int for n in raw)
    if not ok:
        raise AnchorError("lines must be [start, end] integers")
    first, last = raw
    if not 1 <= first <= last <= total:
        raise AnchorError(f"lines {raw} are outside the document (1-{total})")
    if first < section.start or last > section.end:
        raise AnchorError(f"lines {raw} are outside section {section.heading!r}")
    return first, last


def resolve_anchor(anchor: Any, lines: list[str], sections: list[Section]) -> tuple[Section, str]:
    """Verify an anchor and return its section plus the exact source text it names."""

    if not isinstance(anchor, dict) or not str(anchor.get("section", "")).strip():
        raise AnchorError("anchor needs a section")
    if "quote" not in anchor and "lines" not in anchor:
        raise AnchorError("anchor needs a quote or a line range")
    section = find_section(sections, str(anchor["section"]))
    text = ""
    if "lines" in anchor:
        first, last = _line_range(anchor["lines"], section, len(lines))
        text = "\n".join(lines[first - 1 : last])
    if "quote" in anchor:
        text = _verify_quote(str(anchor["quote"]), section, lines)
    return section, text


def _verify_quote(quote: str, section: Section, lines: list[str]) -> str:
    wanted = normalize(quote)
    if not wanted:
        raise AnchorError("quote is empty")
    if wanted not in normalize(section_body(lines, section)):
        raise AnchorError(f"quote not found verbatim in section {section.heading!r}: {wanted!r}")
    return wanted
