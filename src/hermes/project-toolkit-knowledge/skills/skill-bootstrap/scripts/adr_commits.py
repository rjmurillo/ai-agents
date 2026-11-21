# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/git.ts                 (the record parser of getCommitHistoryDetailed, lines
#                                   110-242, replaced here by a parser over raw commit objects)
#   src/lib/adr-writer.ts          (slug, line 137; link extraction, line 100)
#   src/lib/fetchers/adr-date.ts   (isoOrNull, the real-calendar-day rule, lines 43-52)
#   src/lib/first-run-pr-import.ts (isBot, the selection loop of read, dropCoveredCommits and
#                                   dropCommitsOfStoredPrs, lines 73-130 and 160-207)
# Not ported: unquoteGitPath, because the port reads no per-commit file lists.
# Extension E3, breaking_change, has no upstream source.
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_scan.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Commit records, text helpers, pull request selection, and the breaking-change flag.

No I/O, no subprocess, standard library only. The reader in ``adr_scan.py`` lists commit
SHAs with ``git rev-list``, feeds them to ``git cat-file --batch``, and passes each raw
object to ``parse_commit_object``.

Departures from the upstream source, each pinned by a test:

- Commits are parsed from raw objects, never from delimited ``git log`` text. The
  ``cat-file --batch`` output is size-prefixed and the SHA order comes from ``rev-list``,
  so no commit message can forge a record, even one holding NUL bytes that
  ``git hash-object`` wrote past git's own checks. Upstream guarded with a 40-hex
  header check on delimited text.
- A subject is cut at ``MAX_SUBJECT_CHARS`` and a body at ``MAX_BODY_CHARS``, so every
  pattern that runs later has bounded input.
- ``slugify`` folds accented Latin letters to ASCII before it cuts at the first other
  character, so ``Cafe policy`` is ``cafe-policy`` and not ``caf-policy``. A title with no
  ASCII letter or digit gives ``""``, and the caller falls back to ``decision-<sha7>``.
- ``iso_day`` accepts only a real calendar day, as upstream does, and returns the day.
- ``hash_tokens`` reads hex words whole, so ``abc1234`` inside a longer word is not a SHA.
- ``breaking_change`` is new (extension E3, Conventional Commits 1.0.0).
- The commit/PR dedup matches both the merge SHA and a subject ending ``(#N)``. Upstream
  used the SHA for a fresh read and ``(#N)`` for stored rows.

Pull request selection takes an offline export, a JSON list passed with ``--prs-json``.
Upstream fetched merged pull requests from the GitHub API, and this port makes no network
call. Each object needs these fields, under either name:

- ``number``: integer.
- ``title``: string. ``body``: string or null.
- ``url`` or ``html_url``: an ``https://`` string.
- ``merged_at`` or ``mergedAt``: an ISO timestamp, or null when the pull request is not merged.
- ``author`` or ``user``: an object with ``login`` and ``is_bot`` (bool) or ``type`` (``Bot``).
- ``merge_commit_sha``, or ``mergeCommit`` holding ``oid``: the merge commit SHA, when known.

Extra fields are ignored, so the export that ``bootstrap_mine.py --prs-json`` reads works here
when it also carries these fields.

Regex notes: see the module docstring of ``adr_shape.py``; they apply to every module here.
"""

from __future__ import annotations

import codecs
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from adr_reason import extract_reason
from adr_shape import is_release_or_bump_subject

__all__ = [
    "EXCERPT_CHARS",
    "MAX_BODY_CHARS",
    "MAX_SUBJECT_CHARS",
    "SLUG_MAX",
    "CommitRecord",
    "PrRow",
    "breaking_change",
    "commit_pr_number",
    "commit_urls",
    "covering_numbers",
    "covering_pr",
    "excerpt",
    "hash_tokens",
    "iso_day",
    "issue_numbers",
    "one_line",
    "parse_commit_object",
    "sanitize",
    "select_prs",
    "slugify",
    "trailing_pr_number",
    "without_merge_lines",
    "urls_in",
    "word_tokens",
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


# Every pattern below runs on these cut texts, so a hostile message cannot cost more than a
# fixed amount of work per commit or pull request.
MAX_SUBJECT_CHARS = 1000
MAX_BODY_CHARS = 64 * 1024


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
    return subject[:MAX_SUBJECT_CHARS], rest.strip()[:MAX_BODY_CHARS]


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


# ---------------------------------------------------------------------------
# Text helpers (src/lib/adr-writer.ts, src/lib/fetchers/adr-date.ts)
# ---------------------------------------------------------------------------

SLUG_MAX = 60
EXCERPT_CHARS = 1200
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", _A)
_ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", _A)
_URL = re.compile(r"(?:https?|git)://[^\s<>()\[\]\"'`]+", _A)
_WORD_RUN = re.compile(r"[A-Za-z0-9_.-]+", _A)
_HASH = re.compile(r"(?<![0-9A-Za-z_])[0-9a-fA-F]{7,64}(?![0-9A-Za-z_])", _A)
_ISSUE = re.compile(r"(?<![0-9A-Za-z_/&])#([0-9]+)(?![0-9A-Za-z_])", _A)
_SPACE_RUN = re.compile(r"\s+")


def sanitize(text: str, limit: int | None = None) -> str:
    """Normalize line endings, drop NUL and other control bytes, and cut to ``limit`` chars."""
    cleaned = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    return cleaned if limit is None else cleaned[:limit]


def one_line(text: str) -> str:
    """``text`` with each whitespace run, line breaks included, as one space, and trimmed."""
    return _SPACE_RUN.sub(" ", text).strip()


def iso_day(value: object) -> str | None:
    """The leading ``YYYY-MM-DD`` of ``value`` when it is a real calendar day, else None."""
    if not isinstance(value, str):
        return None
    match = _ISO_DAY.match(value.strip())
    if not match:
        return None
    try:
        date.fromisoformat(match.group(0))
    except ValueError:
        return None
    return match.group(0)


def slugify(title: str) -> str:
    """ASCII lowercase words joined by hyphens, at most ``SLUG_MAX`` characters, or ``""``."""
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    return slug[:SLUG_MAX].rstrip("-")


def urls_in(text: str) -> set[str]:
    """Every complete URL in ``text``, trailing sentence punctuation and slashes dropped."""
    found = (match.group(0).rstrip(".,;:!?").rstrip("/") for match in _URL.finditer(text))
    return {url for url in found if url}


def hash_tokens(text: str) -> set[str]:
    """Hex words of 7 to 64 characters, lowercased. A longer word is never split."""
    return {match.group(0).lower() for match in _HASH.finditer(text)}


def issue_numbers(text: str) -> set[int]:
    """Numbers written ``#N`` as a whole token. ``a#12`` and ``/#12`` do not count."""
    return {int(match.group(1)) for match in _ISSUE.finditer(text)}


def word_tokens(text: str) -> set[str]:
    """The whole words of ``text``, lowercased, so an id is found by set membership.

    A word is a run of letters, digits, ``_`` and ``-``: ``D-001`` is in ``see d-001.`` and not
    in ``D-0010``. A word that holds a dot (``v1.2``) is kept whole, without edge dots, so it
    is found in ``(v1.2).`` and not in ``v1.25``.
    """
    words: set[str] = set()
    for found in _WORD_RUN.findall(text):
        run = found.lower()
        words.update(piece for piece in run.split(".") if piece)
        dotted = run.strip(".")
        if "." in dotted:
            words.add(dotted)
    return words


# ---------------------------------------------------------------------------
# Pull request selection and commit/PR dedup (src/lib/first-run-pr-import.ts)
# ---------------------------------------------------------------------------

BODY_CAP = 8000
_BOT_LOGIN = re.compile(r"(?:dependabot|renovate)\b", re.IGNORECASE | re.ASCII)
_BOT_SUFFIX = re.compile(r"\[bot\]\Z", re.IGNORECASE | re.ASCII)
_TRAILING_PR = re.compile(r"\(#([0-9]+)\)\s*\Z", re.ASCII)
_HEX_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}", re.ASCII)


@dataclass(frozen=True)
class PrRow:
    number: int
    title: str
    body: str
    url: str
    merged_day: str
    merge_sha: str | None
    reason: str


def trailing_pr_number(subject: str) -> int | None:
    """The ``N`` of a subject that ends ``(#N)``, as a squash merge writes it."""
    match = _TRAILING_PR.search(subject)
    return int(match.group(1)) if match else None


def _is_bot(item: dict[str, Any]) -> bool:
    user = item.get("author") or item.get("user") or {}
    if not isinstance(user, dict):
        return False
    login = str(user.get("login") or "")
    return (
        user.get("is_bot") is True
        or user.get("type") == "Bot"
        or bool(_BOT_SUFFIX.search(login))
        or bool(_BOT_LOGIN.match(login))
    )


def _merge_sha(item: dict[str, Any]) -> str | None:
    raw = item.get("merge_commit_sha")
    if raw is None and isinstance(item.get("mergeCommit"), dict):
        raw = item["mergeCommit"].get("oid")
    text = raw.lower() if isinstance(raw, str) else ""
    return text if _HEX_SHA.fullmatch(text) else None


def _page_url(item: dict[str, Any]) -> object:
    """The pull request page: ``html_url``, else ``url`` unless that is a REST API address.

    A raw GitHub pull object holds both. Its ``url`` is the API endpoint, on an ``api.`` host
    or under ``/repos/``, and is not the page a reader opens.
    """
    if item.get("html_url"):
        return item["html_url"]
    url = item.get("url")
    if isinstance(url, str):
        parts = urlsplit(url)
        if (parts.hostname or "").startswith("api.") or "/repos/" in parts.path:
            return None
    return url


def _complete(item: dict[str, Any]) -> tuple[int, str, str, str, str] | None:
    """``(number, title, body, url, merged day)`` when the item has every required field."""
    number = item.get("number")
    title = item.get("title")
    url = _page_url(item)
    day = iso_day(item.get("merged_at") or item.get("mergedAt"))
    body = item.get("body")
    if not (isinstance(number, int) and not isinstance(number, bool) and number > 0):
        return None
    if not isinstance(title, str) or not title.strip() or day is None:
        return None
    if not isinstance(url, str) or not url.startswith("https://") or re.search(r"\s", url):
        return None
    text = body.replace("\r\n", "\n").replace("\r", "\n") if isinstance(body, str) else ""
    return number, title.strip()[:MAX_SUBJECT_CHARS], text[:MAX_BODY_CHARS], url, day


def select_prs(items: list[Any], dropped: dict[str, int], base: str | None = None) -> list[PrRow]:
    """The merged, non-bot pull requests whose body states a reason (P9).

    Counts each rejection in ``dropped``: ``pr_incomplete`` (not merged or a field missing),
    ``pr_other_repo``, ``pr_bot``, ``pr_housekeeping`` (a release or version bump title) and
    ``pr_no_reason``. ``base`` is the web address of this repository's origin. A row whose URL
    is not under ``<base>/pull/``, compared without regard to case, is another repository's, so
    it is dropped and covers no commit. With no known origin (``base`` is None) the export
    cannot be checked and every complete row is kept.
    """
    rows: list[PrRow] = []
    for item in items:
        fields = _complete(item) if isinstance(item, dict) else None
        if fields is None:
            dropped["pr_incomplete"] = dropped.get("pr_incomplete", 0) + 1
            continue
        number, title, body, url, day = fields
        if base is not None and not url.lower().startswith(f"{base.lower()}/pull/"):
            dropped["pr_other_repo"] = dropped.get("pr_other_repo", 0) + 1
        elif _is_bot(item):
            dropped["pr_bot"] = dropped.get("pr_bot", 0) + 1
        elif is_release_or_bump_subject(title):
            dropped["pr_housekeeping"] = dropped.get("pr_housekeeping", 0) + 1
        elif not (reason := extract_reason(title, body[:BODY_CAP])):
            dropped["pr_no_reason"] = dropped.get("pr_no_reason", 0) + 1
        else:
            rows.append(PrRow(number, title, body, url, day, _merge_sha(item), reason))
    return rows


def covering_numbers(rows: list[PrRow]) -> tuple[dict[str, int], set[int]]:
    """The merge SHA to number map, and the numbers, of the kept pull requests."""
    return {row.merge_sha: row.number for row in rows if row.merge_sha}, {
        row.number for row in rows
    }


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TASK_LINE = re.compile(r"^[ \t]*[-*][ \t]+\[[ xX]\][^\n]*\n?", re.MULTILINE)
_BLANK_RUN = re.compile(r"\n{3,}")


def excerpt(title: str, body: str) -> str:
    """The quoted source text: template comments and checklist lines are form, not content.

    The body is cut before any pattern runs. ``<!--.*?-->`` is quadratic on a body of many
    unclosed ``<!--``, and only ``EXCERPT_CHARS`` of the result are kept.
    """
    body = body[: EXCERPT_CHARS * 4]
    body = _BLANK_RUN.sub("\n\n", _TASK_LINE.sub("", _HTML_COMMENT.sub("", body)))
    return sanitize(f"{title}\n\n{body}".strip(), EXCERPT_CHARS)


def commit_urls(
    web: tuple[str, str] | None, sha: str, number: int | None
) -> tuple[str | None, str | None]:
    """``(commit URL, pull request URL)`` on a GitHub or GitLab origin, else ``(None, None)``."""
    if web is None:
        return None, None
    kind, base = web
    commit = f"{base}/-/commit/{sha}" if kind == "gitlab" else f"{base}/commit/{sha}"
    pull = f"{base}/pull/{number}" if kind == "github" and number is not None else None
    return commit, pull


def commit_pr_number(record: CommitRecord, promoted: str) -> int | None:
    from_squash = trailing_pr_number(promoted) or trailing_pr_number(record.subject)
    if from_squash is not None:
        return from_squash
    merge = record.subject.startswith("Merge pull request #")
    digits = record.subject[len("Merge pull request #") :].split(" ", 1)[0]
    return int(digits) if merge and digits.isdigit() else None


_MERGE_LINE = re.compile(r"merge (?:pull request|branch)\b", _I)


def without_merge_lines(body: str) -> str:
    """A promoted merge's body without its ``Merge pull request #N from x/y`` line.

    ``resolve_commit_shape`` keeps that line so the ``#N`` survives. It names the pull request
    and gives no reason, so the rationale check must not read it.
    """
    return "\n".join(line for line in body.split("\n") if not _MERGE_LINE.match(line.strip()))


def covering_pr(
    record: CommitRecord, promoted: str, by_sha: dict[str, int], numbers: set[int]
) -> int | None:
    """The number of the kept pull request this commit became (P10), or None.

    The commit's SHA is a kept pull request's merge commit, or a number it names is kept: a
    subject ending ``(#N)``, as stored or promoted, or ``Merge pull request #N``.
    """
    if record.sha.lower() in by_sha:
        return by_sha[record.sha.lower()]
    named = (
        trailing_pr_number(promoted),
        trailing_pr_number(record.subject),
        commit_pr_number(record, promoted),
    )
    return next((number for number in named if number in numbers), None)
