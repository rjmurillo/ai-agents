# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts           (slug, line 137; link extraction, line 100)
#   src/lib/fetchers/adr-date.ts    (isoOrNull, the real-calendar-day rule, lines 43-52)
# Sibling ports: adr_locate.py, adr_scan.py, adr_draft.py, adr_log.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Small text helpers shared by the ADR backfill modules. No I/O, standard library only.

Departures from the upstream source, each pinned by a test:

- ``slugify`` folds accented Latin letters to ASCII before it cuts at the first other
  character, so ``Café policy`` is ``cafe-policy`` and not ``caf-policy``. A title with no
  ASCII letter or digit gives ``""``, and the caller falls back to ``decision-<sha7>``.
- ``iso_day`` accepts only a real calendar day, as upstream does, and returns the day.
- ``hash_tokens`` reads hex words whole, so ``abc1234`` inside a longer word is not a SHA.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

__all__ = [
    "SLUG_MAX",
    "hash_tokens",
    "iso_day",
    "issue_numbers",
    "sanitize",
    "slugify",
    "urls_in",
    "word_present",
]

SLUG_MAX = 60
_A = re.ASCII
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", _A)
_ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", _A)
_URL = re.compile(r"(?:https?|git)://[^\s<>()\[\]\"'`]+", _A)
_TRAILING_PUNCT = re.compile(r"[.,;:!?]+\Z", _A)
_HASH = re.compile(r"(?<![0-9A-Za-z_])[0-9a-fA-F]{7,64}(?![0-9A-Za-z_])", _A)
_ISSUE = re.compile(r"(?<![0-9A-Za-z_/&])#([0-9]+)(?![0-9A-Za-z_])", _A)


def sanitize(text: str, limit: int | None = None) -> str:
    """Normalize line endings, drop NUL and other control bytes, and cut to ``limit`` chars."""
    cleaned = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    return cleaned if limit is None else cleaned[:limit]


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
    found = (_TRAILING_PUNCT.sub("", match.group(0)).rstrip("/") for match in _URL.finditer(text))
    return {url for url in found if url}


def hash_tokens(text: str) -> set[str]:
    """Hex words of 7 to 64 characters, lowercased. A longer word is never split."""
    return {match.group(0).lower() for match in _HASH.finditer(text)}


def issue_numbers(text: str) -> set[int]:
    """Numbers written ``#N`` as a whole token. ``a#12`` and ``/#12`` do not count."""
    return {int(match.group(1)) for match in _ISSUE.finditer(text)}


def word_present(word: str, text: str) -> bool:
    """Is ``word`` in ``text`` as a whole token, ignoring case? ``D-001`` is not in ``D-0010``."""
    pattern = r"(?<![A-Za-z0-9_-])" + re.escape(word) + r"(?![A-Za-z0-9_-])"
    return re.search(pattern, text, re.IGNORECASE | _A) is not None
