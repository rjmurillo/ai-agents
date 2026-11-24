# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/fetchers/docs-decision-log.ts (all of it, P12)
# Extension E1, log_candidates, has no upstream source.
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_log.py, adr_scan.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Decision logs and ledgers, and the candidates they yield (extension E1).

Standard library only. ``read_log_entries`` reads the decision log and ledger files a
repository keeps by hand, never a file over 1 MiB. A numbered log (``## D17 - title``,
``D181: ...``) or a ledger (``id: D-001 | status: test | modified: 2026-10-27``, then text) is
listed from the repository root and ``docs/`` only, because ``docs/decisions/`` is an ADR folder
that ``adr_locate.py`` reads.

Departures from the upstream source, each pinned by a test:

- Upstream used log entries as context. Extension E1 makes an entry that has an id a
  candidate when no existing ADR names its key (``log_candidates``).
- ``entry_date`` returns the day (``YYYY-MM-DD``) through ``adr_commits.iso_day``, which accepts
  only a real calendar day. Upstream returned an ISO instant.
- A sub-heading deeper than its decision's heading (``### Rationale``), or any id-less heading
  after a ledger line, stays inside that decision.
- Upstream's minimum chunk length is not ported.
- The log and heading patterns trim blanks in code instead of in a lazy group, so a long run
  of spaces costs linear time.

Regex notes: see the module docstring of ``adr_shape.py``; they apply to every module here.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from adr_commits import EXCERPT_CHARS, iso_day, sanitize
from adr_docs import ExistingAdrs, fence_after
from adr_locate import read_bounded
from adr_reason import extract_reason

__all__ = [
    "MAX_LOG_CANDIDATES",
    "MAX_LOG_ENTRIES",
    "MAX_LOG_FILES",
    "LogEntry",
    "entry_date",
    "find_log_files",
    "log_candidates",
    "read_log_entries",
    "split_decision_log",
]

_I = re.IGNORECASE | re.ASCII
_A = re.ASCII

_LOG_FILE = re.compile(r"(?:decisions?[-_]log|decisions|.*ledger.*)\.md\Z", _I)
_LOG_DIRS = ("", "docs")
MAX_LOG_FILES = 20
MAX_LOG_ENTRIES = 5000
# Blanks and closing marks come off in ``_heading_text``: a lazy group before ``[ \t]*#*[ \t]*\Z``
# is quadratic on a long run of spaces.
_HEADING = re.compile(r"#{1,6}[ \t]+(.+)", _A)
# `id: X`, or a bare id-like token (D-001, D181, ADR-7, D-1.2), at the start of a top-level line.
# A dot joins a bare id only before a digit, so the dot of `D-1.` or `D-1.md` stays out.
_BARE_ID = r"[A-Za-z]{1,6}-?[0-9]+(?:\.[0-9]+)*"
_ID_IN_HEADING = re.compile(rf"(?:id:[ \t]*([\w.-]+)|({_BARE_ID}))(?!\w)", _I)
_ID_START = re.compile(rf"(?:[-*][ \t]+)?(?:id:[ \t]*([\w.-]+)|({_BARE_ID}))(?!\w)", _I)
# `https://...` is a URL, not a field: a colon followed by // never starts a value.
_FIELD = re.compile(r"([a-z_]+):(?!//)\s*(.*)\Z", _I | re.DOTALL)
# No ``\s*`` around the mark: it is quadratic on a long run of spaces. Segments are stripped.
_FIELD_SEPARATOR = re.compile(r"[·|]")
_MIN_ENTRY_CHARS = 20
_TITLE_MAX = 120
_DATE_KEYS = ("date", "decided", "modified")


@dataclass(frozen=True, slots=True)
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
    """Decision log file paths, relative to ``root``, at the root and in ``docs/``.

    A symlinked file is left out here, before the ``MAX_LOG_FILES`` quota, because
    ``read_bounded`` refuses it and it would take a real log's place."""
    found: list[str] = []
    for folder in _LOG_DIRS:
        try:
            base = root.resolve()
            names = [
                entry.name
                for entry in (root / folder).iterdir()
                if _LOG_FILE.fullmatch(entry.name)
                and entry.is_file()
                and not entry.is_symlink()
                and base in entry.resolve().parents
            ]
        except OSError:
            continue
        found.extend(f"{folder}/{n}" if folder else n for n in names if _LOG_FILE.fullmatch(n))
    return sorted(found)


def _heading_text(line: str) -> str | None:
    """The text of a ``#`` heading line without its closing marks, or None for any other line."""
    match = _HEADING.fullmatch(line)
    if match is None:
        return None
    text = match[1].rstrip(" \t").rstrip("#").rstrip(" \t")
    return text or match[1][:1]


def _fields_of(line: str) -> list[tuple[str, str]]:
    """The ``key: value`` segments of ``line`` in source order; a key may repeat."""
    found = (_FIELD.fullmatch(segment.strip()) for segment in _FIELD_SEPARATOR.split(line))
    return [(match[1].lower(), match[2].strip()) for match in found if match]


def _heading_title(heading: str) -> str:
    """The first line with its ``key: value`` segments removed."""
    parts = re.split(r"([·|])", heading)
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
        if not _FIELD.fullmatch(segment.strip())  # the same field syntax as ``_fields_of``
    ]
    return " ".join(segment.strip() for segment in kept).strip()


def _blocks(content: str) -> list[_Block]:
    blocks: list[_Block] = []
    fence: str | None = None
    outer = 0  # level of the last id-less heading, such as the ``# Ledger`` around the records
    for line in content.replace("\r\n", "\n").split("\n"):
        after = fence_after(fence, line, any_indent=True)
        if fence is not None or after is not None:
            # Lines inside a fenced block belong to the enclosing entry, whatever they look like.
            fence = after
            if blocks:
                blocks[-1].lines.append(line)
            continue
        heading = _heading_text(line)
        top_level = not line[:1].isspace()
        if heading:
            found = _ID_IN_HEADING.match(heading)
        else:
            found = _ID_START.match(line) if top_level else None
        level = len(line) - len(line.lstrip("#")) if heading else 0
        if (
            heading
            and not found
            and blocks
            and blocks[-1].id
            and (blocks[-1].level or outer + 1) < level
        ):
            # A sub-heading stays with its decision: deeper than a ``## D-7`` heading, or for a
            # ledger record (level 0) deeper than the section around it. A peer section ends it.
            blocks[-1].lines.append(line)
        elif heading or found:
            ident = (
                (found[1] or found[2]).rstrip(".") or None if found else None
            )  # "id: D-7." is D-7
            outer = level if heading and not found else outer
            blocks.append(_Block(ident, heading, level, [line]))
        elif blocks:
            blocks[-1].lines.append(line)
    return blocks


def _without_closing_hashes(text: str) -> str:
    """``## Title ##`` without its closing marks. ``\\s+#+\\Z`` is quadratic on spaces."""
    body = text.rstrip("#")
    return body.rstrip() if body != text and body[-1:].isspace() else text


def _entry_of(block: _Block) -> LogEntry:
    text = "\n".join(block.lines).strip()
    first = re.sub(r"^#+[ \t]+", "", block.lines[0])
    first = re.sub(r"^[-*][ \t]+", "", first).strip()
    if block.heading:
        remainder = _heading_title(_without_closing_hashes(first))
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
    fence: str | None = None
    for line in text.split("\n"):
        after = fence_after(fence, line, any_indent=True)
        if fence is not None or after is not None:  # an example in a fence is not metadata
            fence = after
            continue
        for key, value in _fields_of(re.sub(r"^\s*[-*][ \t]+", "", line)):
            if key not in fields and iso_day(value):  # the first valid day per key
                fields[key] = value
    for key in _DATE_KEYS:
        day = iso_day(fields.get(key))
        if day:
            return day
    return None


def read_log_entries(
    root: Path, dropped: dict[str, int] | None = None
) -> tuple[list[tuple[str, LogEntry]], int, int]:
    """``(entries, files, skipped)`` for the decision log files under ``root``.

    An entry is ``(relative file, entry)``. ``files`` counts the log files found, and
    ``skipped`` counts those that were unreadable, over ``MAX_READ_BYTES``, or past the first
    ``MAX_LOG_FILES`` in path order. A file keeps its first ``MAX_LOG_ENTRIES`` entries, and the
    rest count under ``dropped["log_over_limit"]``, so memory stays bounded.
    """
    entries: list[tuple[str, LogEntry]] = []
    files = find_log_files(root)
    skipped = max(0, len(files) - MAX_LOG_FILES)
    for rel in files[:MAX_LOG_FILES]:
        text = read_bounded(root / rel)
        if text is None:
            skipped += 1
        else:
            parsed = split_decision_log(text)
            entries.extend((rel, entry) for entry in parsed[:MAX_LOG_ENTRIES])
            if dropped is not None:
                dropped["log_over_limit"] += max(0, len(parsed) - MAX_LOG_ENTRIES)
    return entries, len(files), skipped


MAX_LOG_CANDIDATES = 1000


def _entry_keys(entries: list[tuple[str, LogEntry]]) -> list[str]:
    """The key a draft records for each entry with an id: ``<id>--`` and 8 hex digits of the
    SHA-256 of its title, one word that adding, removing, or reordering other entries does not
    change. An entry with no id gets ``""``. Keys compare without regard to case, as
    ``ExistingAdrs.names_id`` does. A key already taken, by a same-title twin or a literal id,
    gets ``-2``, ``-3`` and so on, so no key repeats; same-title twins differ only by order."""
    keys: list[str] = []
    taken: set[str] = set()
    following: dict[str, int] = {}
    for _rel, e in entries:
        if not e.id:
            keys.append("")
            continue
        base = key = f"{e.id}--{sha256(e.title.encode()).hexdigest()[:8]}"
        count = following.get(base.lower(), 1)
        while key.lower() in taken:
            count += 1
            key = f"{base}-{count}"
        following[base.lower()] = count
        taken.add(key.lower())
        keys.append(key)
    return keys


def _log_candidate(rel: str, entry: LogEntry, ident: str, key: str) -> dict[str, Any]:
    rest = entry.text.split("\n", 1)[1] if "\n" in entry.text else ""
    return {
        "id": ident,
        "kind": "decision-log",
        "title": sanitize(entry.title).strip(),
        "reason": extract_reason(entry.title, rest),
        "excerpt": sanitize(entry.text, EXCERPT_CHARS),
        "date": entry_date(entry.text),
        "source": {"file": rel, "entry_id": key},
        "signals": [],
    }


def log_candidates(
    root: Path, existing: ExistingAdrs, dropped: dict[str, int]
) -> tuple[list[dict[str, Any]], int, int]:
    """E1: ``(candidates, log files, log files skipped)``.

    An entry with an id is documented when an ADR names its key, or names the bare id while that
    id is unique, case aside, in the logs read; otherwise it is a candidate. A log file yields
    at most ``MAX_LOG_CANDIDATES``, and the rest count under ``log_over_limit``. The candidate id
    is ``log-`` plus the entry key, so twins of one id get distinct ids.
    """
    found: list[dict[str, Any]] = []
    per_file: dict[str, int] = {}
    entries, files, skipped = read_log_entries(root, dropped)
    keys = _entry_keys(entries)
    total = Counter(e.id.lower() for _rel, e in entries if e.id)
    for (rel, entry), key in zip(entries, keys, strict=True):
        if entry.id is None:
            dropped["log_no_id"] += 1
        elif existing.names_id(key) or (
            total[entry.id.lower()] == 1 and existing.names_id(entry.id)
        ):
            dropped["already_documented"] += 1
        elif per_file.get(rel, 0) >= MAX_LOG_CANDIDATES:
            dropped["log_over_limit"] += 1
        else:
            per_file[rel] = per_file.get(rel, 0) + 1
            found.append(_log_candidate(rel, entry, f"log-{key}", key))
    return found, files, skipped
