"""Text parsing shared by the skillify helpers.

Frontmatter, markdown sections, list counting, and tokenizing. Stdlib only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
SEPARATOR_RE = re.compile(r"^\s*\|[\s:|-]+\|?\s*$")
BOM = "\ufeff"
TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    "a an and are as at be but by do does for from has have how in into is it its "
    "not of on or our that the their then this to use used using was when which "
    "will with you your".split()
)


class SkillifyError(Exception):
    """Input the helper cannot act on. Maps to exit code 1."""


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split YAML-ish frontmatter into top-level string values and the body.

    Reads only top-level scalar keys, folded or literal blocks, and quoted
    strings. Nested maps fold into their parent key and are ignored.
    """
    lines = text.lstrip(BOM).splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "\n".join(lines)
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, "\n".join(lines)
    return _top_level_values(lines[1:end]), "\n".join(lines[end + 1 :])


def _top_level_values(lines: Sequence[str]) -> dict[str, str]:
    parts: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        match = KEY_RE.match(line)
        if match:
            current = match.group(1)
            parts[current] = [match.group(2)]
        elif current is not None and line.strip():
            parts[current].append(line.strip())
    return {key: _clean_scalar(value) for key, value in parts.items()}


def _clean_scalar(parts: Sequence[str]) -> str:
    first = parts[0].strip()
    if first[:1] in {">", "|"}:
        first = ""
    joined = " ".join(p for p in [first, *parts[1:]] if p).strip()
    if len(joined) >= 2 and joined[0] == joined[-1] and joined[0] in {'"', "'"}:
        quote = joined[0]
        joined = joined[1:-1]
        if quote == '"':
            joined = joined.replace('\\"', '"')
    return joined


@dataclass(frozen=True)
class Section:
    """A markdown section: its normalized name and the lines under it."""

    name: str
    lines: tuple[str, ...]


def split_sections(body: str) -> list[Section]:
    """Return every heading with its content, ignoring headings in code fences."""
    headings: list[tuple[int, int, str]] = []
    lines = body.splitlines()
    fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        match = None if fence else HEADING_RE.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2)))
    return [_section_at(lines, headings, n) for n in range(len(headings))]


def _section_at(lines: Sequence[str], headings: Sequence[tuple[int, int, str]], n: int) -> Section:
    index, level, title = headings[n]
    end = len(lines)
    for later_index, later_level, _ in headings[n + 1 :]:
        if later_level <= level:
            end = later_index
            break
    return Section(normalize_heading(title), tuple(lines[index + 1 : end]))


def normalize_heading(title: str) -> str:
    """Lowercase, drop punctuation, and join words with `-`: `Anti-Patterns` -> `anti-patterns`."""
    return "-".join(TOKEN_RE.findall(title.lower()))


def count_items(lines: Sequence[str]) -> int:
    """Count bullets, numbered items, and table data rows outside code fences."""
    count = 0
    fence = False
    table: list[str] = []
    for line in [*lines, ""]:
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence:
            continue
        if line.lstrip().startswith("|"):
            table.append(line)
            continue
        count += _table_rows(table)
        table = []
        if BULLET_RE.match(line):
            count += 1
    return count


def _table_rows(table: Sequence[str]) -> int:
    if not table:
        return 0
    has_header = any(SEPARATOR_RE.match(row) for row in table)
    data = [row for row in table if not SEPARATOR_RE.match(row)]
    return len(data) - (1 if has_header else 0)


def tokenize(text: str) -> frozenset[str]:
    """Lowercase word tokens, minus stop words, with one trailing `s` folded off."""
    tokens = set()
    for raw in TOKEN_RE.findall(text.lower()):
        if raw in STOPWORDS or len(raw) < 3:
            continue
        tokens.add(_fold_plural(raw))
    return frozenset(tokens)


def _fold_plural(word: str) -> str:
    """Drop one trailing `s` from a plural, keeping `status`, `process`, `analysis`."""
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word
