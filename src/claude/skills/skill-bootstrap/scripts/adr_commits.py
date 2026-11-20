# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/git.ts                 (the record parser of getCommitHistoryDetailed, lines
#                                   110-242, replaced here by a parser over raw commit objects)
#   src/lib/context-from-graph.ts  (decisionShapedRows, lines 84-109)
# Not ported: unquoteGitPath, because the port reads no per-commit file lists.
# Extension E3, breaking_change, has no upstream source.
# Sibling ports: adr_shape.py, adr_docs.py, adr_reason.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Pure classifiers over commit records: parse a commit object, filter, flag breaking changes.

No I/O, no subprocess, standard library only. The reader in ``adr_git.py`` lists commit
SHAs with ``git rev-list``, feeds them to ``git cat-file --batch``, and passes each raw
object to ``parse_commit_object``.

Departures from the upstream source, each pinned by a test:

- ``is_decision_shaped_title`` strips any ``type(scope)!:`` prefix and applies the
  fix-shaped test to the type. Upstream's ``^\\w+\\([^)]*\\):`` alternative dropped
  every scoped commit except ``feat(...)``.
- Commits are parsed from raw objects, never from delimited ``git log`` text. The
  ``cat-file --batch`` output is size-prefixed and the SHA order comes from ``rev-list``,
  so no commit message can forge a record, even one holding NUL bytes that
  ``git hash-object`` wrote past git's own checks. Upstream guarded with a 40-hex
  header check on delimited text.
- ``breaking_change`` is new (extension E3, Conventional Commits 1.0.0).

Regex notes. Module-level patterns compile with ``re.ASCII`` so ``\\b``, ``\\w``, ``\\d`` and
case folding match the JavaScript source. ``$`` without a multiline flag is ``\\Z``
here, because Python's ``$`` also matches before a trailing newline. ASCII ``\\s`` does not match Unicode spaces such as U+00A0, which JavaScript's ``\\s`` does.
"""

from __future__ import annotations

import codecs
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, TypeVar

__all__ = [
    "CommitRecord",
    "DecisionRow",
    "breaking_change",
    "decision_shaped_rows",
    "is_decision_shaped_title",
    "parse_commit_object",
]

_I = re.IGNORECASE | re.ASCII
_A = re.ASCII

# ---------------------------------------------------------------------------
# P7: commit records from raw objects (src/lib/git.ts, replaced)
# ---------------------------------------------------------------------------

_AUTHOR = re.compile(
    r"(?P<name>.*) <[^<>]*> (?P<ts>-?[0-9]{1,12}) (?P<sign>[+-])(?P<hh>[0-9]{2})(?P<mm>[0-9]{2})\Z",
    _A | re.DOTALL,
)


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    subject: str
    author: str
    date: str
    body: str


def _split_object(raw: bytes) -> tuple[bytes, bytes]:
    """Headers and message, split at the first blank line. No blank line: all headers."""
    if raw.startswith(b"\n"):
        return b"", raw[1:]
    head, sep, message = raw.partition(b"\n\n")
    return (head, message) if sep else (raw, b"")


def _header_values(head: bytes) -> dict[bytes, bytes]:
    """The first value of each header. Continuation lines (a gpgsig block) are skipped."""
    values: dict[bytes, bytes] = {}
    for line in head.split(b"\n"):
        if line.startswith(b" "):
            continue
        key, _, value = line.partition(b" ")
        values.setdefault(key, value)
    return values


def _decode(data: bytes, encoding: bytes | None) -> str:
    """Decode with the commit's ``encoding`` header, or UTF-8 when it is absent or unusable."""
    if encoding:
        try:
            name = codecs.lookup(encoding.decode("ascii")).name
            return data.decode(name, "replace")
        except (LookupError, ValueError):
            pass
    return data.decode("utf-8", "replace")


def _author_fields(author: str) -> tuple[str, str]:
    """The author name and the author date as an ISO 8601 instant, or an empty date."""
    match = _AUTHOR.fullmatch(author)
    if not match:
        return author.partition(" <")[0], ""
    offset = timedelta(hours=int(match["hh"]), minutes=int(match["mm"]))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    try:
        zone = timezone(-offset if match["sign"] == "-" else offset)
        date = (epoch + timedelta(seconds=int(match["ts"]))).astimezone(zone).isoformat()
    except (OverflowError, ValueError, OSError):
        date = ""
    return match["name"], date


def _subject_and_body(message: str) -> tuple[str, str]:
    """Subject is the first paragraph joined by spaces, body is the rest, as ``%s`` and ``%b``."""
    text = message.replace("\r\n", "\n").lstrip("\n")
    first, _, rest = text.partition("\n\n")
    subject = " ".join(part.strip() for part in first.split("\n") if part.strip())
    return subject, rest.strip()


def parse_commit_object(sha: str, raw: bytes) -> CommitRecord:
    """Parse the raw bytes of one commit object as ``git cat-file commit`` prints them.

    The author name and date come from the first ``author`` header. The message is
    everything after the first blank line, decoded with the ``encoding`` header when
    it names a known text codec and as UTF-8 otherwise. Text that looks like a header,
    holds NUL bytes, or imitates a record boundary is message text. A malformed object
    never raises: a missing author gives empty fields, a bad timestamp gives an empty date.
    """
    head, message = _split_object(raw)
    headers = _header_values(head)
    author_text = _decode(headers.get(b"author", b""), headers.get(b"encoding"))
    author, date = _author_fields(author_text)
    subject, body = _subject_and_body(_decode(message, headers.get(b"encoding")))
    return CommitRecord(sha, subject, author, date, body)


# ---------------------------------------------------------------------------
# P8: decision-shaped filter (src/lib/context-from-graph.ts)
# ---------------------------------------------------------------------------

# A commit or PR shaped like a fix, a test, a chore or an issue reference. Upstream also
# dropped ``^\w+\([^)]*\):``, which removed every scoped commit. Here the word list is
# applied to the conventional type instead.
_FIX_SHAPED = re.compile(
    r"^(?:fix(?:es|ed)?|bug|hotfix|tests?|ci|style|chore|build|docs?|refactor|perf|revert"
    r"|bump|deps?)\b|^#\d+",
    _I,
)
_CODE_PLATFORMS = frozenset({"git", "github", "gitlab"})
# `type(scope)!:` with an optional leading issue number on what follows.
_ANY_TYPE_PREFIX = re.compile(r"^([a-z]+)(?:\([^)]*\))?!?:\s*(?:#\d+\s*)?", _I)
# Words a choice is written in.
_DECISION_SHAPED = re.compile(
    r"\b(?:adopt|switch(?:ed)? to|move to|migrate|replace[sd]?\b.*\bwith|instead of|deprecate"
    r"|drop support|requires?|must|always|never|no longer|policy|convention|prefer"
    r"|standardi[sz]e|forbid|disallow)\b|^use\b",
    _I,
)


class DecisionRow(Protocol):
    """A listed decision: any object with a title and a source platform."""

    @property
    def title(self) -> str: ...

    @property
    def platform(self) -> str | None: ...


_Row = TypeVar("_Row", bound=DecisionRow)


def is_decision_shaped_title(title: str) -> bool:
    """Does a commit or PR title read as a decision, and not as a fix?

    Any ``type(scope)!:`` prefix is stripped. A fix-shaped type (fix, docs, chore, ...)
    drops the title. Otherwise the rest is judged: "feat: fix retry policy" is the
    fix it is, and "feat(api): switch to gRPC" is kept.
    """
    prefix = _ANY_TYPE_PREFIX.match(title)
    rest = title[prefix.end() :] if prefix else title
    if prefix and _FIX_SHAPED.search(prefix.group(1)):
        return False
    return not _FIX_SHAPED.search(rest) and bool(_DECISION_SHAPED.search(rest))


def decision_shaped_rows(rows: Iterable[_Row]) -> list[_Row]:
    """The non-docs rows that read as decisions.

    Rows from chat and ticket importers are already chosen by the importer, so only
    git, github and gitlab rows are filtered.
    """
    kept: list[_Row] = []
    for row in rows:
        if row.platform == "docs":
            continue
        if (row.platform or "") not in _CODE_PLATFORMS or is_decision_shaped_title(row.title):
            kept.append(row)
    return kept


# ---------------------------------------------------------------------------
# E3: breaking-change signal (extension, Conventional Commits 1.0.0)
# ---------------------------------------------------------------------------

_BREAKING_SUBJECT = re.compile(r"^[a-z]+(?:\([^)]*\))?!:", _I)
# The token is uppercase by the specification. BREAKING-CHANGE is its synonym.
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:[ \t]+\S", re.MULTILINE | _A)
_FOOTER_LINE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:[ \t]+\S", _A)
_BLANK_LINES = re.compile(r"\n[ \t]*\n", _A)


def breaking_change(subject: str, body: str) -> bool:
    """Does the commit mark itself as a breaking change?

    True for a ``type!:`` or ``type(scope)!:`` subject, and for a ``BREAKING CHANGE:``
    or ``BREAKING-CHANGE:`` line that begins a line in the footer. The footer is the
    last paragraph, or an earlier one when only trailer paragraphs (such as
    ``Co-Authored-By``) follow it. The phrase in mid-body prose does not count.
    """
    if _BREAKING_SUBJECT.search(subject.strip()):
        return True
    paragraphs = _BLANK_LINES.split(body.replace("\r\n", "\n").strip())
    for paragraph in reversed(paragraphs):
        if _BREAKING_FOOTER.search(paragraph):
            return True
        if not _is_trailer_paragraph(paragraph):
            return False
    return False


def _is_trailer_paragraph(paragraph: str) -> bool:
    lines = [line for line in paragraph.split("\n") if line.strip()]
    return bool(lines) and all(_FOOTER_LINE.match(line) for line in lines)
