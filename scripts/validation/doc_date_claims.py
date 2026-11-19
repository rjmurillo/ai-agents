#!/usr/bin/env python3
"""Pure matching logic for the doc-date-drift gate.

This module answers questions about lines of Markdown and about path names.
Git reads, scope, and the CLI live in ``check_doc_date_drift.py``.

Four rules share it:

* ``header-pair``: a ``Last Updated`` or ``Last Reviewed`` date paired with a
  ``Next Review`` date (:func:`header_dates`, :func:`header_problems`).
* ``subject-drift``: one subject (a URL or a quoted title) carries a different
  year on two lines of the same skill (:func:`claims_for_line`).
* ``version-drift``: one named tool carries a different version on two lines of
  the same skill (:func:`claims_for_line`).
* ``stale-as-of``: an "as of" date older than a date a diff added within three
  lines (:func:`as_of_claim`, :func:`dates_on_line`).

Years compare at year granularity: a subject on one line dated ``2026-03-04``
and on another dated ``2026`` agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from frontmatter_split import split_leading_frontmatter

IGNORE_MARKER = "doc-date-drift: ignore"
_IGNORE_WITH_REASON = re.compile(re.escape(IGNORE_MARKER) + r"\s+--\s+\S")

RULE_HEADER = "header-pair"
RULE_SUBJECT = "subject-drift"
RULE_VERSION = "version-drift"
RULE_AS_OF = "stale-as-of"

DEFAULT_REVIEW_INTERVAL_DAYS = 90
AS_OF_WINDOW_LINES = 3
_MIN_TITLE_CHARS = 8
_MAX_NAME_WORDS = 2

_HTML_COMMENT = re.compile(r"<!--.*?-->")
_URL = re.compile(r"https?://[^\s<>\"'`\]]+", re.IGNORECASE)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_TITLE = re.compile(r"[\"“]([^\"“”\n]+)[\"”]")
_YEAR = re.compile(r"(?<![\w./-])((?:19|20)\d{2})(?!\d)")
_UPDATED_YEAR = re.compile(r"\bupdated(?:\s+in)?\s+((?:19|20)\d{2})\b", re.IGNORECASE)
_BLOCKQUOTE_LEAD = re.compile(r"^\s*>+\s?")

# Skill-tree layout: canonical sources only. Generated mirrors are not read.
_SKILL_PATTERNS = (
    re.compile(r"^(?:src/claude|\.claude)/skills/([^/]+)/"),
    re.compile(r"^templates/skills/([^/]+)\.SKILL\.md\.tmpl$"),
    re.compile(r"^templates/skills/([^/]+)/"),
    re.compile(r"^docs/skills/([^/]+)\.md$"),
)
_NOT_SKILL_NAMES = frozenset({"partials", "README"})
_GENERATED_SKILL_FILE = "SKILL.md"
_TREE_SUFFIXES = (".md", ".md.tmpl")


def has_reasoned_ignore(lines: list[str], number: int, text: str) -> bool:
    """Return whether the line, or the line above it, carries a reasoned ignore.

    ``number`` is 1-based. A marker without ``-- <reason>`` does not count.
    """
    if _IGNORE_WITH_REASON.search(text):
        return True
    return number >= 2 and bool(_IGNORE_WITH_REASON.search(lines[number - 2]))


def skill_name_for(path: str) -> str | None:
    """Return the skill a tracked path belongs to, or None."""
    for pattern in _SKILL_PATTERNS:
        match = pattern.match(path)
        if match and match.group(1) not in _NOT_SKILL_NAMES:
            return match.group(1)
    return None


def skill_tree_paths(name: str, tracked: set[str]) -> list[str]:
    """Return the tracked canonical Markdown paths of one skill, sorted.

    Generated ``SKILL.md`` files are excluded: their source is the template.
    """
    prefixes = (
        f"src/claude/skills/{name}/",
        f"templates/skills/{name}/",
        f".claude/skills/{name}/",
    )
    exact = {f"templates/skills/{name}.SKILL.md.tmpl", f"docs/skills/{name}.md"}
    found = []
    for path in tracked:
        in_tree = path in exact or path.startswith(prefixes)
        generated = path.rsplit("/", 1)[-1] == _GENERATED_SKILL_FILE
        if in_tree and path.endswith(_TREE_SUFFIXES) and not generated:
            found.append(path)
    return sorted(found)


@dataclass(frozen=True)
class Claim:
    """One subject-and-value assertion made by one line."""

    rule: str
    key: str
    value: str


def normalize_url(url: str) -> str:
    """Return a URL key: no scheme, ``www.``, fragment, or trailing slash; casefolded."""
    bare = _SCHEME.sub("", url.strip()).split("#", 1)[0].casefold()
    if bare.startswith("www."):
        bare = bare[len("www.") :]
    return bare.rstrip("/")


def _trim_url(url: str) -> str:
    """Drop sentence punctuation, and an unbalanced closing bracket, from a URL match."""
    trimmed = url.rstrip(".,;:!?")
    while trimmed.endswith(")") and trimmed.count(")") > trimmed.count("("):
        trimmed = trimmed[:-1].rstrip(".,;:!?")
    return trimmed


def _normalize_title(title: str) -> str:
    """Casefold, strip punctuation, and collapse whitespace."""
    return " ".join(re.sub(r"[^\w\s]", "", title).casefold().split())


def _subject_year(text: str) -> str | None:
    """Return the "updated" year if present, else the largest year, else None."""
    updated = _UPDATED_YEAR.search(text)
    if updated:
        return updated.group(1)
    years = _YEAR.findall(text)
    return max(years) if years else None


# Words that precede a version without naming the thing that has it, and
# structural labels ("Step 1.2") whose number is not a version.
_STOP_WORDS = frozenset(
    "a an and are as at by for from in is of on only or the to via was were with using use uses "
    "version versions ver v release releases tested requires require needs need pinned pin "
    "supports support run runs install installed upgrade current latest minimum maximum min max "
    "step steps section sections phase stage tier level gate rule item row exit code adr issue pr "
    "line page pages chapter figure table see no number".split()
)
_NAME_TOKEN = re.compile(r"[A-Za-z][\w.+-]*")
_VERSION = r"v?\d+\.\d+(?:\.\d+)?(?![\w]|\.\d)"
_AT_VERSION = re.compile(
    r"(?<![\w@./-])(@?[A-Za-z][\w.-]*(?:/[\w.-]+)?)@v?(\d+\.\d+(?:\.\d+)?)(?![\w]|\.\d)"
)
_TICK_VERSION = re.compile(r"`([^`\s@]+)`\s+v?(\d+\.\d+(?:\.\d+)?)(?![\w]|\.\d)")
_WORD_VERSION = re.compile(r"(?<![\w.@/`-])(?P<v>v?)(?P<ver>\d+\.\d+(?:\.\d+)?)(?![\w]|\.\d)")
_HISTORY = re.compile(
    r"\b(?:since|added in|introduced|deprecated|removed|before|after|prior to|until|changelog)\b"
    r"|>=|<=|<|>",
    re.IGNORECASE,
)


def _name_before(prefix: str) -> list[str]:
    """Return up to two name tokens that end right before a version, nearest last."""
    if not prefix[-1:].isspace():
        return []
    words: list[str] = []
    for token in reversed(prefix.split()):
        if len(words) == _MAX_NAME_WORDS or not _NAME_TOKEN.fullmatch(token):
            break
        if token.casefold() in _STOP_WORDS:
            break
        words.append(token)
    words.reverse()
    return words


def _is_proper_name(prefix: str, words: list[str]) -> bool:
    """Return whether a bare ``X.Y`` follows a capitalised name that is not the first word."""
    return words[-1][0].isupper() and len(prefix.split()) > len(words)


def _word_version_claims(text: str) -> list[Claim]:
    """Return ``name X.Y(.Z)`` claims; a bare ``X.Y`` needs a capitalised name."""
    found = []
    for match in _WORD_VERSION.finditer(text):
        words = _name_before(text[: match.start()])
        if not words:
            continue
        bare_minor = not match.group("v") and match.group("ver").count(".") == 1
        if bare_minor and not _is_proper_name(text[: match.start()], words):
            continue
        found.append(Claim(RULE_VERSION, " ".join(words).casefold(), match.group("ver")))
    return found


def _version_claims(text: str) -> list[Claim]:
    """Return version claims for a line already stripped of URLs and comments."""
    if _HISTORY.search(_BLOCKQUOTE_LEAD.sub("", text)):
        return []
    found = [
        Claim(RULE_VERSION, m.group(1).casefold(), m.group(2)) for m in _AT_VERSION.finditer(text)
    ]
    found += [
        Claim(RULE_VERSION, m.group(1).casefold(), m.group(2)) for m in _TICK_VERSION.finditer(text)
    ]
    return found + _word_version_claims(text)


def claims_for_line(text: str) -> list[Claim]:
    """Return every subject-year and name-version claim the line makes, deduplicated."""
    cleaned = _HTML_COMMENT.sub(" ", text)
    urls = [normalize_url(_trim_url(url)) for url in _URL.findall(cleaned)]
    without_urls = _URL.sub(" ", cleaned)
    titles = [_normalize_title(t) for t in _TITLE.findall(without_urls)]
    titles = [title for title in titles if len(title) >= _MIN_TITLE_CHARS]
    year = _subject_year(_TITLE.sub(" ", without_urls))
    found: list[Claim] = []
    if year:
        found += [Claim(RULE_SUBJECT, f"url:{url}", year) for url in urls]
        found += [Claim(RULE_SUBJECT, f"title:{title}", year) for title in titles]
    found += _version_claims(without_urls)
    return list(dict.fromkeys(found))


@dataclass(frozen=True)
class HeaderDate:
    """One review-header date and where it sits."""

    kind: str  # "last" or "next"
    line: int
    value: date
    section: str = "body"  # "frontmatter" or "body"


_HEADER = re.compile(
    r"^\s*(?:[-*+]\s+)?(?:\*\*)?"
    r"(?P<label>last[\s_-]*(?:updated|reviewed)|next[\s_-]*review)"
    r"(?:\*\*)?\s*:\s*(?:\*\*)?\s*[\"']?(?P<date>\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def _parse_iso(text: str) -> date | None:
    """Return the calendar date, or None when ``text`` is not one."""
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def header_dates(
    lines: list[str],
    first_line: int = 1,
    section: str = "body",
    skip_lines: frozenset[int] | set[int] = frozenset(),
) -> list[HeaderDate]:
    """Read Last Updated, Last Reviewed, and Next Review dates from ``lines``.

    ``first_line`` is the file line number of ``lines[0]``; ``skip_lines`` holds
    file line numbers to ignore, such as lines inside a code fence.
    """
    found = []
    for offset, text in enumerate(lines):
        number = first_line + offset
        match = _HEADER.match(text)
        parsed = _parse_iso(match.group("date")) if match else None
        if match is None or parsed is None or number in skip_lines:
            continue
        kind = "next" if match.group("label").casefold().startswith("next") else "last"
        found.append(HeaderDate(kind, number, parsed, section))
    return found


def file_header_dates(
    lines: list[str], skip_lines: frozenset[int] | set[int] = frozenset()
) -> list[HeaderDate]:
    """Read header dates from a whole file, keeping frontmatter and body apart."""
    text = "\n".join(lines)
    front, body = split_leading_frontmatter(text)
    if body == text:
        return header_dates(lines, skip_lines=skip_lines)
    front_lines = front.split("\n") if front else []
    body_start = len(front_lines) + 3
    found = header_dates(front_lines, first_line=2, section="frontmatter", skip_lines=skip_lines)
    return found + header_dates(
        lines[body_start - 1 :], first_line=body_start, skip_lines=skip_lines
    )


@dataclass(frozen=True)
class HeaderProblem:
    """A Next Review date that is inconsistent with its Last Updated date."""

    next_line: int
    last_line: int
    reason: str
    suggested: date


def suggest_next_review(last: date, prior_interval_days: int | None) -> date:
    """Return ``last`` plus the prior interval, or 90 days when there is none."""
    days = prior_interval_days if prior_interval_days and prior_interval_days > 0 else None
    return last + timedelta(days=days or DEFAULT_REVIEW_INTERVAL_DAYS)


def _pair(dates: list[HeaderDate], section: str) -> tuple[HeaderDate | None, list[HeaderDate]]:
    """Return the latest ``last`` date and every ``next`` date of one section."""
    lasts = [d for d in dates if d.section == section and d.kind == "last"]
    nexts = [d for d in dates if d.section == section and d.kind == "next"]
    return (max(lasts, key=lambda d: d.value) if lasts else None), nexts


def _prior_interval(base_dates: list[HeaderDate], section: str) -> int | None:
    """Return the base version's Next minus Last in days, or None when unreadable."""
    last, nexts = _pair(base_dates, section)
    if last is None or not nexts:
        return None
    return (nexts[0].value - last.value).days


def header_problems(
    dates: list[HeaderDate],
    base_dates: list[HeaderDate],
    added: set[int],
    head_date: date,
) -> list[HeaderProblem]:
    """Return inconsistent pairs where the diff added one of the pair's lines."""
    problems = []
    for section in ("frontmatter", "body"):
        last, nexts = _pair(dates, section)
        if last is None:
            continue
        suggested = suggest_next_review(last.value, _prior_interval(base_dates, section))
        for review in nexts:
            if last.line not in added and review.line not in added:
                continue
            if review.value <= last.value:
                reason = f"Next Review {review.value} is not after Last Updated {last.value}"
            elif review.value < head_date:
                reason = f"Next Review {review.value} is before the commit date {head_date}"
            else:
                continue
            problems.append(HeaderProblem(review.line, last.line, reason, suggested))
    return problems


_MONTHS = {
    name: index
    for index, names in enumerate(
        (
            "january jan",
            "february feb",
            "march mar",
            "april apr",
            "may",
            "june jun",
            "july jul",
            "august aug",
            "september sep sept",
            "october oct",
            "november nov",
            "december dec",
        ),
        1,
    )
    for name in names.split()
}
_AS_OF = re.compile(
    r"\b(?:as of|rechecked on|rechecked|verified on|checked on)\b\s*[:,]?\s*"
    r"(?P<iso>\d{4}-\d{2}-\d{2})|"
    r"\b(?:as of|rechecked on|rechecked|verified on|checked on)\b\s*[:,]?\s*"
    r"(?P<month>[A-Za-z]{3,9})\.?\s+(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
_MONTH_YEAR = re.compile(r"\b(?P<month>[A-Za-z]{3,9})\.?\s+(?P<year>\d{4})\b")


@dataclass(frozen=True)
class PartialDate:
    """A date as written: a full day, or a month only."""

    value: date
    month_only: bool
    text: str

    def is_older_than(self, other: PartialDate) -> bool:
        """Return whether this date is older, at this date's own granularity."""
        if self.month_only:
            return (self.value.year, self.value.month) < (other.value.year, other.value.month)
        return self.value < other.value


def _month_year(month: str, year: str, text: str) -> PartialDate | None:
    number = _MONTHS.get(month.casefold())
    return PartialDate(date(int(year), number, 1), True, text) if number else None


def as_of_claim(text: str) -> PartialDate | None:
    """Return the date an "as of" / "rechecked" / "verified" phrase states, or None."""
    match = _AS_OF.search(text)
    if match is None:
        return None
    if match.group("iso"):
        parsed = _parse_iso(match.group("iso"))
        return PartialDate(parsed, False, match.group("iso")) if parsed else None
    return _month_year(
        match.group("month"), match.group("year"), f"{match.group('month')} {match.group('year')}"
    )


def dates_on_line(text: str) -> list[PartialDate]:
    """Return every ISO date and ``Month YYYY`` on the line."""
    found = []
    for raw in _ISO_DATE.findall(text):
        parsed = _parse_iso(raw)
        if parsed:
            found.append(PartialDate(parsed, False, raw))
    for match in _MONTH_YEAR.finditer(text):
        month_year = _month_year(match.group("month"), match.group("year"), match.group(0))
        if month_year:
            found.append(month_year)
    return found
