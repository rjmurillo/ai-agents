# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/git.ts                 (unquoteGitPath and the commit record parser of
#                                   getCommitHistoryDetailed, lines 110-242)
#   src/lib/context-from-graph.ts  (decisionShapedRows, lines 84-109)
# Extension E3, breaking_change, has no upstream source.
# Sibling ports: adr_shape.py, adr_docs.py, adr_reason.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Pure classifiers over commit records: parse ``git log``, filter, flag breaking changes.

No I/O, no subprocess, standard library only. The CLI that runs ``git log`` with
``GIT_LOG_ARGS`` passes its output to ``parse_commit_records``.

Departures from the upstream source, each pinned by a test:

- ``decision_shaped_rows`` strips any ``type(scope)!:`` prefix and applies the
  fix-shaped test to the type. Upstream's ``^\\w+\\([^)]*\\):`` alternative dropped
  every scoped commit except ``feat(...)``.
- The commit record format uses NUL bytes, which git refuses in a commit message,
  so a message cannot forge a record header. The 40-hex sha check stays as a second
  guard.
- ``breaking_change`` is new (extension E3, Conventional Commits 1.0.0).

Regex notes. Module-level patterns compile with ``re.ASCII`` so ``\\b``, ``\\w``, ``\\d`` and
case folding match the JavaScript source. ``$`` without a multiline flag is ``\\Z``
here, because Python's ``$`` also matches before a trailing newline. ASCII ``\\s`` does not match Unicode spaces such as U+00A0, which JavaScript's ``\\s`` does.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, TypeVar

__all__ = [
    "GIT_LOG_ARGS",
    "CommitRecord",
    "DecisionRow",
    "breaking_change",
    "decision_shaped_rows",
    "is_decision_shaped_title",
    "parse_commit_records",
    "unquote_git_path",
]

_I = re.IGNORECASE | re.ASCII
_A = re.ASCII

# ---------------------------------------------------------------------------
# P7: commit record parsing that refuses forged headers (src/lib/git.ts)
# ---------------------------------------------------------------------------

# Arguments for ``git log``. Git refuses a NUL byte in a commit message, so a NUL-based
# marker cannot be forged by one. Each record is
#   NUL "COMMIT" NUL sha NUL subject NUL author NUL date NUL body NUL "END" NL files...
# where files come from ``--name-only``. Pass these after ``git log``.
GIT_LOG_ARGS: tuple[str, ...] = (
    "--format=%x00COMMIT%x00%H%x00%s%x00%aN%x00%aI%x00%b%x00END",
    "--name-only",
)
_RECORD_MARKER = "\x00COMMIT\x00"
_RECORD_END = "\x00END"
_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z", _A)
_C_ESCAPES = {
    "a": 7,
    "b": 8,
    "t": 9,
    "n": 10,
    "v": 11,
    "f": 12,
    "r": 13,
    '"': 34,
    "\\": 92,
}
_OCTAL_ESCAPE = re.compile(r"[0-3][0-7]{2}", _A)


@dataclass(frozen=True)
class CommitRecord:
    sha: str
    subject: str
    author: str
    date: str
    body: str
    files: tuple[str, ...]


def unquote_git_path(path: str) -> str:
    """Undo git's C-quoting of a path with non-ASCII bytes, a quote or a backslash.

    ``"docs/page-\\303\\251.md"`` becomes ``docs/page-\u00e9.md``. An unquoted path, and
    a quoted one that holds an escape git does not write, is returned unchanged.
    """
    if len(path) < 2 or not path.startswith('"') or not path.endswith('"'):
        return path
    body = path[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        ch = body[i]
        if ch != "\\":
            out += ch.encode("utf-8", "replace")
            i += 1
            continue
        octal = _OCTAL_ESCAPE.match(body, i + 1)
        if octal:
            out.append(int(octal.group(0), 8))
            i += 4
            continue
        escaped = _C_ESCAPES.get(body[i + 1 : i + 2])
        if escaped is None:
            return path
        out.append(escaped)
        i += 2
    return out.decode("utf-8", "replace")


def _is_record_header(chunk: str) -> bool:
    return bool(_FULL_SHA.match(chunk.split("\x00", 1)[0]))


def _record_from(text: str) -> CommitRecord | None:
    parts = text.split("\x00", 4)
    if len(parts) < 5:
        return None
    sha, subject, author, date, rest = parts
    end = rest.rfind(_RECORD_END)
    body = rest if end < 0 else rest[:end]
    tail = "" if end < 0 else rest[end + len(_RECORD_END) :]
    files = tuple(unquote_git_path(line.strip()) for line in tail.split("\n") if line.strip())
    return CommitRecord(sha, subject, author, date, body.rstrip(), files)


def parse_commit_records(raw: str) -> list[CommitRecord]:
    """Parse ``git log`` output made with ``GIT_LOG_ARGS``.

    Only a marker followed by a full 40-hex lowercase sha starts a record. A marker
    with any other sha stays part of the previous record's text, so it cannot
    forge a record. A record with no ``END`` terminator keeps all its text as the body.
    Text before the first record is ignored.
    """
    texts: list[str] = []
    for chunk in raw.replace("\r\n", "\n").split(_RECORD_MARKER)[1:]:
        if _is_record_header(chunk):
            texts.append(chunk)
        elif texts:
            texts[-1] += _RECORD_MARKER + chunk
    records = (_record_from(text) for text in texts)
    return [record for record in records if record is not None]


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
