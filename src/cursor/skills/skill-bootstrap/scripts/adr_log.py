# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream file: src/lib/fetchers/docs-decision-log.ts (all of it, P12).
# Sibling ports: adr_text.py, adr_locate.py, adr_scan.py, adr_draft.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Read decision log and ledger files a repository keeps by hand.

A numbered log (``## D17 - title``, ``D181: ...``) or a ledger
(``id: D-001 | status: test | modified: 2026-10-27``, then text). Only the repository root and
``docs/`` are listed. ``docs/decisions/`` is an ADR folder and ``adr_locate.py`` reads it.
Reads the working tree, never a file over 1 MiB. Standard library only.

Departures from the upstream source:

- Upstream used these entries as context. Extension E1 makes an entry that has an id a
  candidate when no existing ADR names that id (``adr_scan.py``).
- ``entry_date`` returns the day (``YYYY-MM-DD``) through ``adr_text.iso_day``, which accepts
  only a real calendar day. Upstream returned an ISO instant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from adr_locate import read_bounded
from adr_text import iso_day

__all__ = ["LogEntry", "entry_date", "find_log_files", "split_decision_log"]

_A = re.ASCII
_I = re.IGNORECASE | re.ASCII
_LOG_FILE = re.compile(r"(?:decisions?[-_]log|decisions|.*ledger.*)\.md\Z", _I)
_LOG_DIRS = ("", "docs")
_HEADING = re.compile(r"#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*\Z", _A)
# `id: X`, or a bare id-like token (D-001, D181, ADR-7), at the start of a top-level line.
_ID_START = re.compile(r"(?:[-*][ \t]+)?(?:id:[ \t]*([\w.-]+)|([A-Za-z]{1,6}-?[0-9]+))(?!\w)", _I)
_ID_IN_HEADING = re.compile(r"(?:id:[ \t]*([\w.-]+)|([A-Za-z]{1,6}-?[0-9]+))(?!\w)", _I)
# `https://...` is a URL, not a field: a colon followed by // never starts a value.
_FIELD = re.compile(r"([a-z_]+):(?!//)\s*(.*)\Z", _I | re.DOTALL)
_FIELD_SEPARATOR = re.compile(r"\s*[·|]\s*")
_FENCE = re.compile(r"\s*(```|~~~)", _A)
_MIN_ENTRY_CHARS = 20
_TITLE_MAX = 120
_DATE_KEYS = ("date", "decided", "modified")


@dataclass(frozen=True)
class LogEntry:
    id: str | None
    heading: str | None
    title: str
    text: str


@dataclass
class _Block:
    id: str | None
    heading: str | None
    level: int
    lines: list[str]


def find_log_files(root: Path) -> list[str]:
    """Decision log file paths, relative to ``root``, at the root and in ``docs/``."""
    found: list[str] = []
    for folder in _LOG_DIRS:
        try:
            names = [entry.name for entry in (root / folder).iterdir() if entry.is_file()]
        except OSError:
            continue
        found.extend(f"{folder}/{n}" if folder else n for n in names if _LOG_FILE.fullmatch(n))
    return sorted(found)


def _fields_of(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for segment in _FIELD_SEPARATOR.split(line):
        match = _FIELD.fullmatch(segment.strip())
        if match:
            fields[match[1].lower()] = match[2].strip()
    return fields


def _heading_title(heading: str) -> str:
    """The first line with its ``key: value`` segments removed."""
    parts = re.split(r"\s*([·|])\s*", heading)
    out = parts[0].strip()
    for index in range(1, len(parts) - 1, 2):
        segment = parts[index + 1].strip()
        if segment and not _FIELD.fullmatch(segment):
            out += f" {parts[index]} {segment}"
    return out


def _text_outside_fields(line: str) -> str:
    kept = [
        segment
        for segment in _FIELD_SEPARATOR.split(line)
        if not re.fullmatch(r"[a-z_]+:(?:\s.*)?", segment.strip(), _I | re.DOTALL)
    ]
    return " ".join(kept).strip()


def _blocks(content: str) -> list[_Block]:
    blocks: list[_Block] = []
    fence: str | None = None
    for line in content.replace("\r\n", "\n").split("\n"):
        mark = _FENCE.match(line)
        if fence is not None or mark:
            # Lines inside a fenced block belong to the enclosing entry, whatever they look like.
            if mark and (fence is None or mark[1] == fence):
                fence = mark[1] if fence is None else None
            if blocks:
                blocks[-1].lines.append(line)
            continue
        heading = _HEADING.fullmatch(line)
        top_level = not line[:1].isspace()
        if heading:
            found = _ID_IN_HEADING.match(heading[1])
        else:
            found = _ID_START.match(line) if top_level else None
        if heading or found:
            ident = (found[1] or found[2]) if found else None
            level = len(line) - len(line.lstrip("#")) if heading else 0
            blocks.append(_Block(ident, heading[1] if heading else None, level, [line]))
        elif blocks:
            blocks[-1].lines.append(line)
    return blocks


def _entry_of(block: _Block) -> LogEntry:
    text = "\n".join(block.lines).strip()
    first = re.sub(r"^#+[ \t]+", "", block.lines[0])
    first = re.sub(r"^[-*][ \t]+", "", first).strip()
    if block.heading:
        remainder = _heading_title(re.sub(r"\s+#+\Z", "", first))
    else:
        remainder = _text_outside_fields(first)
    body = next((line.strip() for line in block.lines[1:] if line.strip()), "")
    title = (remainder or body or block.id or "")[:_TITLE_MAX]
    return LogEntry(block.id, block.heading, title, text)


def split_decision_log(content: str) -> list[LogEntry]:
    """One entry per id line or heading. A leading id-less H1 is the file's title, not an entry."""
    blocks = _blocks(content)
    if blocks and blocks[0].level == 1 and blocks[0].id is None:
        blocks.pop(0)
    entries = (_entry_of(block) for block in blocks)
    return [
        entry
        for entry in entries
        if entry.title
        and (
            entry.id is not None
            or (entry.heading is not None and len(entry.text) >= _MIN_ENTRY_CHARS)
        )
    ]


def entry_date(text: str) -> str | None:
    """The first real calendar day in a ``date``, ``decided`` or ``modified`` field, else None.

    No git fallback: one file holds many decisions, so the file's history says nothing true
    about when any single entry was decided.
    """
    fields: dict[str, str] = {}
    for line in text.split("\n"):
        for key, value in _fields_of(re.sub(r"^\s*[-*][ \t]+", "", line)).items():
            fields.setdefault(key, value)
    for key in _DATE_KEYS:
        day = iso_day(fields.get(key))
        if day:
            return day
    return None


def read_log_entries(root: Path) -> list[tuple[str, LogEntry]]:
    """``(relative file, entry)`` for every entry of every decision log file under ``root``."""
    entries: list[tuple[str, LogEntry]] = []
    for rel in find_log_files(root):
        text = read_bounded(root / rel)
        if text is not None:
            entries.extend((rel, entry) for entry in split_decision_log(text))
    return entries
