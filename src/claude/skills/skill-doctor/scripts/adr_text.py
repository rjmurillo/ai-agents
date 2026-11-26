"""Text parsing for ADR files: frontmatter, prose lines, status, and cited-path cleaning.

Stdlib only. Pure functions over lines and strings; no filesystem or git access.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from typing import Any

STATUS_HEADING = re.compile(r"^#{2,3}\s+status\b", re.IGNORECASE)
BACKTICK = re.compile(r"`([^`\n]+)`")
PATHLIKE = re.compile(r"^[A-Za-z0-9_.@+-][A-Za-z0-9_.@+/-]*$")
PLACEHOLDER = re.compile(r"YYYY|MM-DD|NNN|XXX|path/to", re.IGNORECASE)
FILE_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}$")
# Matched against a line with its leading blanks stripped, so one blank run stays linear.
TABLE_SEPARATOR = re.compile(r"\|?\s*:?-{3,}")
STATUS_WORDS = frozenset(
    {"accepted", "proposed", "draft", "approved", "superseded", "deprecated", "rejected"}
)
# An ADR number: one to six digits after any leading zeros, as file names allow. The digit
# bound keeps a long run of zeros or digits linear and keeps `int()` within its digit limit.
ADR_NUMBER = r"ADR-0*(\d{1,6})\b"
# The largest scan file adr_drift.py writes and report_adr.py reads.
SCAN_MAX_BYTES = 5_000_000
# The largest ADR file read. A larger one goes to read_errors unread.
ADR_MAX_BYTES = 1_000_000

SETUP = "Setup"

NUMBERING = "Numbering"
LINKS = "Links"
HISTORY = "History"
GROUPS = (SETUP, NUMBERING, LINKS, HISTORY)


def _strip_comment(value: str) -> str:
    """Drop a YAML comment: a `#` after whitespace. A linear scan, since `\\s+#` is quadratic."""
    for index in range(1, len(value)):
        if value[index] == "#" and value[index - 1].isspace():
            value = value[:index]
            break
    return value.strip().strip("'\"")


def _scalar(raw: str) -> Any:
    value = _strip_comment(raw)
    if value.startswith("[") and value.endswith("]"):
        return [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
    return value


def parse_frontmatter(lines: Sequence[str]) -> tuple[dict[str, Any], dict[str, int], int]:
    """Parse simple top-level YAML keys: (keys, 1-based line of each key, first body line index)."""
    if not lines or lines[0].strip() != "---":
        return {}, {}, 0
    keys: dict[str, Any] = {}
    key_lines: dict[str, int] = {}
    current: str | None = None
    for index in range(1, min(len(lines), 80)):
        line = lines[index]
        if line.strip() == "---":
            return keys, key_lines, index + 1
        top = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if top:
            current = top.group(1)
            keys[current] = _scalar(top.group(2))
            key_lines[current] = index + 1
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and current is not None:
            existing = keys[current]
            values = existing if isinstance(existing, list) else []
            values.append(_strip_comment(item.group(1)))
            keys[current] = values
    return {}, {}, 0


def prose_lines(lines: Sequence[str], start: int = 0) -> Iterator[tuple[int, str]]:
    """Yield (1-based line number, text), skipping fenced code and HTML comments."""
    fenced = False
    commented = False
    for index in range(start, len(lines)):
        line = lines[index]
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if commented or stripped.startswith("<!--"):
            # On a line inside a comment or opening one, every comment is cut out and the
            # text between them stays live. A comment opened mid-line is not tracked.
            live, commented = _cut_comments(line, commented)
            if live.strip():
                yield index + 1, live
            continue
        yield index + 1, line


def _cut_comments(line: str, commented: bool) -> tuple[str, bool]:
    """The text outside `<!-- ... -->` on one line, and whether a comment is still open."""
    parts: list[str] = []
    index = 0
    while index < len(line):
        if commented:
            end = line.find("-->", index)
            if end < 0:
                return "".join(parts), True
            commented, index = False, end + 3
            continue
        start = line.find("<!--", index)
        if start < 0:
            parts.append(line[index:])
            break
        parts.append(line[index:start])
        commented, index = True, start + 4
    return "".join(parts), commented


def h1_number(text: str) -> int | None:
    match = re.match(rf"^#\s+{ADR_NUMBER}", text) or re.match(r"^#\s+0*(\d{1,6})\.\s", text)
    return int(match.group(1)) if match else None


def h1_form(text: str) -> str | None:
    if re.match(r"^#\s+ADR-\d+\s*:", text):
        return "adr-colon"
    if re.match(r"^#\s+\d+\.\s", text):
        return "number-dot"
    return None


def doc_status(frontmatter: dict[str, Any], lines: Sequence[str], start: int) -> str:
    """Lowercase status text: frontmatter first, then a Status section or line."""
    value = frontmatter.get("status")
    if isinstance(value, str) and value:
        return value.lower()
    prose = list(prose_lines(lines, start))
    in_section = False
    for index, (_, line) in enumerate(prose):
        if STATUS_HEADING.match(line):
            in_section = True
            continue
        if in_section:
            if line.startswith("#"):
                return ""
            if line.strip():
                return line.strip().lower()
            continue
        following = prose[index + 1][1] if index + 1 < len(prose) else ""
        inline = _inline_status(line, following)
        if inline is not None:
            return inline
    return ""


def _inline_status(line: str, following: str) -> str | None:
    """`Status: x`, a `- Status: x` bullet, or a two-cell `| Status | x |` row.

    A row with more cells is a table header, so `| Status | Deciders | Date |` names
    columns, not a status. A two-cell row above a `|---|` separator is a header too,
    unless its second cell is a status word, as in a key and value table.
    """
    if line.lstrip().startswith("|"):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0].strip("*").lower() != "status":
            return None
        value = cells[1].strip("*").strip().lower()
        header = TABLE_SEPARATOR.match(following.lstrip()) is not None
        return None if header and status_word(value) not in STATUS_WORDS else value
    match = re.match(r"^\s*(?:[-*]\s+)?\**status\**\s*:\s*\**\s*(.+)$", line, re.IGNORECASE)
    return match.group(1).strip().lower() if match else None


def status_word(status: str) -> str:
    match = re.match(r"[a-z]+", status.strip("*_ ").lower())
    return match.group(0) if match else ""


def clean_path(token: str) -> str | None:
    value = re.sub(r":\d+(?:-\d+)?$", "", token.strip())
    if not PATHLIKE.match(value) or "/" not in value or PLACEHOLDER.search(value):
        return None
    if value.startswith(("/", "~", "./", "..")) or ".." in value or "//" in value:
        return None
    last = value.rstrip("/").rsplit("/", 1)[-1]
    if not (value.endswith("/") or FILE_EXTENSION.search(last)):
        return None
    return value


def folder_rel(posix: str) -> str:
    """A folder's repo-relative path with the repository root as `""`, never `"."`."""
    return "" if posix == "." else posix


def rel_join(rel: str, name: str) -> str:
    """A file's repo-relative path: the bare name when its folder is the root."""
    return f"{rel}/{name}" if rel else name


def display_rel(rel: str) -> str:
    """A folder's path as shown in JSON and reports: `"."` for the repository root."""
    return rel or "."
