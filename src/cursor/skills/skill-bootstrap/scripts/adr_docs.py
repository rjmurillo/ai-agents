# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/fetchers/docs-conventions.ts  (the rule-section classifier, lines 21-63)
#   src/lib/fetchers/docs.ts              (splitIntoSections and the per-section filter,
#                                          lines 162-170 and 275-279)
#   src/lib/fetchers/docs-decision-log.ts (all of it, P12)
#   src/lib/adr-writer.ts                 (linkedFromAdrs, lines 100-120: ExistingAdrs)
# Sibling ports: adr_shape.py, adr_commits.py, adr_reason.py, adr_locate.py, adr_scan.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Pure classifiers for README, CONTRIBUTING and changelog sections that state a rule.

No file reads, no I/O, standard library only. The caller reads the Markdown and
passes the text. Upstream's minimum chunk length and co-change rule inference are
not ported.

Regex notes. Module-level patterns compile with ``re.ASCII`` so ``\\b``, ``\\w``, ``\\d`` and
case folding match the JavaScript source. ``$`` without a multiline flag is ``\\Z``
here, because Python's ``$`` also matches before a trailing newline. ASCII ``\\s`` does not match Unicode spaces such as U+00A0, which JavaScript's ``\\s`` does.

Decision logs and ledgers:

Read decision log and ledger files a repository keeps by hand.

A numbered log (``## D17 - title``, ``D181: ...``) or a ledger
(``id: D-001 | status: test | modified: 2026-10-27``, then text). Only the repository root and
``docs/`` are listed. ``docs/decisions/`` is an ADR folder and ``adr_locate.py`` reads it.
Reads the working tree, never a file over 1 MiB. Standard library only.

Departures from the upstream source:

- Upstream used these entries as context. Extension E1 makes an entry that has an id a
  candidate when no existing ADR names that id (``adr_scan.py``).
- ``entry_date`` returns the day (``YYYY-MM-DD``) through ``adr_commits.iso_day``, which accepts
  only a real calendar day. Upstream returned an ISO instant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple

from adr_commits import (
    EXCERPT_CHARS,
    hash_tokens,
    iso_day,
    issue_numbers,
    sanitize,
    urls_in,
    word_tokens,
)
from adr_locate import read_bounded
from adr_reason import extract_reason

__all__ = [
    "CHANGELOG_FILES",
    "CONTRIBUTING_FILES",
    "README_FILES",
    "DocKind",
    "ExistingAdrs",
    "LogEntry",
    "RuleSection",
    "entry_date",
    "find_log_files",
    "is_rule_section",
    "is_versioned_release_heading",
    "log_candidates",
    "rule_sections",
    "section_body",
    "split_decision_log",
    "split_into_sections",
]

_I = re.IGNORECASE | re.ASCII
_A = re.ASCII

# ---------------------------------------------------------------------------
# P13: rule sections of README, CONTRIBUTING and changelog
# (src/lib/fetchers/docs-conventions.ts, docs.ts)
# ---------------------------------------------------------------------------

README_FILES: tuple[str, ...] = ("README.md",)
CONTRIBUTING_FILES: tuple[str, ...] = (
    "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
)
CHANGELOG_FILES: tuple[str, ...] = (
    "CHANGELOG.md",
    "docs/changelog.md",
    "docs/CHANGELOG.md",
    "changelog.md",
)

DocKind = Literal["readme", "contributing", "changelog"]

# A line that states an obligation or prohibition.
_RULE_MARKER = re.compile(
    r"\b(?:must(?: not)?|never|always|every|do not|don't|required?|ensure|make sure|should)\b",
    _I,
)
# Headings under which a README section can be a rule. CONTRIBUTING needs no heading.
_CONVENTION_HEADING = re.compile(
    r"changelog|contribut|convention|guideline|\brules?\b|policy|versioning|release process"
    r"|commit|pull request|branch|review|style|deprecat|workflow|development|process"
    r"|branching|how to|standards?",
    _I,
)
# Headings a changelog uses for policy rather than history.
_CHANGELOG_POLICY_HEADING = re.compile(
    r"versioning|convention|policy|deprecat|contribut|guideline|\brules?\b|how to", _I
)
# Keep a Changelog's category headings: entries of one release, never policy.
_CHANGELOG_CATEGORY = re.compile(r"^(?:added|changed|deprecated|removed|fixed|security)\Z", _I)
# `[1.2.0] - 2026-01-01`, `2026-07-07`, `v2`, `Unreleased`: a release entry, never a rule.
_RELEASE_HEADING = re.compile(r"^\[?v?\d+(?:\.\d+)|^\[?unreleased\b|\d{4}-\d{2}(?:-\d{2})?", _I)
_VERSIONED_RELEASE_HEADING = re.compile(r"^release:?\s+v?\d", _I)
_H2_HEADING = re.compile(r"##\s+(.+)\Z", _A)
_NEXT_TOP_HEADING = re.compile(r"\n(?=#\s)", _A)
_TRAILING_RULE = re.compile(r"\n+-{3,}\s*\Z", _A)


class RuleSection(NamedTuple):
    heading: str
    body: str


def is_versioned_release_heading(heading: str) -> bool:
    """``Release: 1.2.0 batch landing``, ``Release 2.0``: a heading that names a version.

    "Release process" and "Releasing the installer" carry no version, so they are not
    release entries.
    """
    return bool(_VERSIONED_RELEASE_HEADING.search(heading.strip()))


def section_body(kind: DocKind, body: str) -> str:
    """Cut a changelog section where the next top-level heading starts.

    A changelog that uses ``# 1.2.0`` as a release heading puts the whole release
    inside the previous section's text.
    """
    return _NEXT_TOP_HEADING.split(body)[0].strip() if kind == "changelog" else body


def is_rule_section(kind: DocKind, heading: str, body: str) -> bool:
    """Does this section state a rule of the repository?

    A changelog policy section is a rule by its heading. Other kinds need a rule marker
    in the body, and a README also needs a convention heading.
    """
    if kind == "changelog":
        h = heading.strip()
        return not (
            _RELEASE_HEADING.search(h)
            or _CHANGELOG_CATEGORY.search(h)
            or not _CHANGELOG_POLICY_HEADING.search(h)
        )
    if not _RULE_MARKER.search(body):
        return False
    return kind == "contributing" or bool(_CONVENTION_HEADING.search(heading))


def split_into_sections(content: str) -> list[tuple[str | None, str]]:
    """Split Markdown on ``## `` headings into (heading, body) pairs.

    Content before the first heading is its own section with heading None. Line
    endings are normalised first, which upstream does not do for CRLF files.
    """
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in content.replace("\r\n", "\n").split("\n"):
        heading = _H2_HEADING.match(line)
        if heading:
            sections.append((heading.group(1).strip(), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections]


def rule_sections(kind: DocKind, markdown: str) -> list[RuleSection]:
    """The sections of ``markdown`` that state a rule, in document order.

    Headingless preamble is skipped. A trailing ``---`` rule is removed from each body.
    Upstream's minimum chunk length and the co-change rule inference are not ported.
    """
    found: list[RuleSection] = []
    for heading, raw in split_into_sections(markdown):
        if not heading:
            continue
        body = _TRAILING_RULE.sub("", section_body(kind, raw)).strip()
        if is_rule_section(kind, heading, body):
            found.append(RuleSection(heading, body))
    return found


# ---------------------------------------------------------------------------
# Decision logs and ledgers (src/lib/fetchers/docs-decision-log.ts)
# ---------------------------------------------------------------------------

_LOG_FILE = re.compile(r"(?:decisions?[-_]log|decisions|.*ledger.*)\.md\Z", _I)
_LOG_DIRS = ("", "docs")
# Blanks and closing marks come off in ``_heading_text``: a lazy group before ``[ \t]*#*[ \t]*\Z``
# is quadratic on a long run of spaces.
_HEADING = re.compile(r"#{1,6}[ \t]+(.+)", _A)
# `id: X`, or a bare id-like token (D-001, D181, ADR-7), at the start of a top-level line.
_ID_START = re.compile(r"(?:[-*][ \t]+)?(?:id:[ \t]*([\w.-]+)|([A-Za-z]{1,6}-?[0-9]+))(?!\w)", _I)
_ID_IN_HEADING = re.compile(r"(?:id:[ \t]*([\w.-]+)|([A-Za-z]{1,6}-?[0-9]+))(?!\w)", _I)
# `https://...` is a URL, not a field: a colon followed by // never starts a value.
_FIELD = re.compile(r"([a-z_]+):(?!//)\s*(.*)\Z", _I | re.DOTALL)
# No ``\s*`` around the mark: it is quadratic on a long run of spaces. Segments are stripped.
_FIELD_SEPARATOR = re.compile(r"[·|]")
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


def _heading_text(line: str) -> str | None:
    """The text of a ``#`` heading line without its closing marks, or None for any other line."""
    match = _HEADING.fullmatch(line)
    if match is None:
        return None
    text = match[1].rstrip(" \t").rstrip("#").rstrip(" \t")
    return text or match[1][:1]


def _fields_of(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for segment in _FIELD_SEPARATOR.split(line):
        match = _FIELD.fullmatch(segment.strip())
        if match:
            fields[match[1].lower()] = match[2].strip()
    return fields


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
        if not re.fullmatch(r"[a-z_]+:(?:\s.*)?", segment.strip(), _I | re.DOTALL)
    ]
    return " ".join(segment.strip() for segment in kept).strip()


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
        heading = _heading_text(line)
        top_level = not line[:1].isspace()
        if heading:
            found = _ID_IN_HEADING.match(heading)
        else:
            found = _ID_START.match(line) if top_level else None
        if heading or found:
            ident = (found[1] or found[2]) if found else None
            level = len(line) - len(line.lstrip("#")) if heading else 0
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


class ExistingAdrs:
    """What the existing ADRs name: hashes, URLs, ``#N`` numbers, and plain words."""

    _MIN_SHA_PREFIX = 7

    def __init__(self, texts: list[tuple[str, str]]) -> None:
        self.words: set[str] = set()
        self.hashes: set[str] = set()
        self.urls: set[str] = set()
        self.numbers: set[int] = set()
        for _path, text in texts:
            self.words |= word_tokens(text)
            self.hashes |= hash_tokens(text)
            self.urls |= urls_in(text)
            self.numbers |= issue_numbers(text)

    def _names_sha(self, sha: str) -> bool:
        full = sha.lower()
        return any(
            full[:size] in self.hashes for size in range(self._MIN_SHA_PREFIX, len(full) + 1)
        )

    def names(self, shas: tuple[str, ...], urls: tuple[str, ...], number: int | None) -> bool:
        """Does an ADR hold one of these SHAs (or a 7+ character prefix), one of these URLs, or ``#N``?"""
        if any(self._names_sha(sha) for sha in shas):
            return True
        if any(url.rstrip("/") in self.urls for url in urls):
            return True
        return number is not None and number in self.numbers

    def names_id(self, ident: str) -> bool:
        """Does an ADR name this decision-log id as a whole word?"""
        return ident.lower() in self.words


def log_candidates(
    root: Path, existing: ExistingAdrs, dropped: dict[str, int]
) -> list[dict[str, Any]]:
    """E1: a decision-log entry that has an id and is named by no ADR is a candidate."""
    found: list[dict[str, Any]] = []
    taken: set[str] = set()
    for rel, entry in read_log_entries(root):
        if entry.id is None:
            dropped["log_no_id"] += 1
        elif existing.names_id(entry.id):
            dropped["already_documented"] += 1
        else:
            ident = f"log-{entry.id}"
            suffix = 1
            while ident in taken:
                suffix += 1
                ident = f"log-{entry.id}.{suffix}"
            taken.add(ident)
            rest = entry.text.split("\n", 1)[1] if "\n" in entry.text else ""
            found.append(
                {
                    "id": ident,
                    "kind": "decision-log",
                    "title": sanitize(entry.title).strip(),
                    "reason": extract_reason(entry.title, rest),
                    "excerpt": sanitize(entry.text, EXCERPT_CHARS),
                    "date": entry_date(entry.text),
                    "source": {"file": rel, "entry_id": entry.id},
                    "signals": [],
                }
            )
    return found
