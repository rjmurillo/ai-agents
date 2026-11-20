# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream file: src/lib/first-run-pr-import.ts (isBot, the selection loop of read,
#   dropCoveredCommits and dropCommitsOfStoredPrs, lines 73-130 and 160-207).
# Sibling ports: adr_text.py, adr_locate.py, adr_scan.py, adr_draft.py, adr_log.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Select decision pull requests from an offline export and drop the commits they replace.

Upstream fetched merged pull requests from the GitHub API. This port makes no network call:
the caller passes a JSON list exported through the host's own tooling (``--prs-json``).

Export shape, a list of objects. Each object needs these fields, under either name:

- ``number``: integer.
- ``title``: string. ``body``: string or null.
- ``url`` or ``html_url``: an ``https://`` string.
- ``merged_at`` or ``mergedAt``: an ISO timestamp, or null when the pull request is not merged.
- ``author`` or ``user``: an object with ``login`` and ``is_bot`` (bool) or ``type`` (``Bot``).
- ``merge_commit_sha``, or ``mergeCommit`` holding ``oid``: the merge commit SHA, when known.

Extra fields are ignored, so the export that ``bootstrap_mine.py --prs-json`` reads works here
when it also carries these fields.

Departures from the upstream source: the commit/PR dedup matches both the merge SHA and a
subject ending ``(#N)``. Upstream used the SHA for a fresh read and ``(#N)`` for stored rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from adr_reason import extract_reason
from adr_shape import is_release_or_bump_subject
from adr_text import iso_day

__all__ = ["PrRow", "covering_numbers", "is_covered", "select_prs", "trailing_pr_number"]

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


def _complete(item: dict[str, Any]) -> tuple[int, str, str, str, str] | None:
    """``(number, title, body, url, merged day)`` when the item has every required field."""
    number = item.get("number")
    title = item.get("title")
    url = item.get("url") or item.get("html_url")
    day = iso_day(item.get("merged_at") or item.get("mergedAt"))
    body = item.get("body")
    if not (isinstance(number, int) and not isinstance(number, bool) and number > 0):
        return None
    if not isinstance(title, str) or not title.strip() or day is None:
        return None
    if not isinstance(url, str) or not url.startswith("https://") or re.search(r"\s", url):
        return None
    text = body.replace("\r\n", "\n").replace("\r", "\n") if isinstance(body, str) else ""
    return number, title.strip(), text, url, day


def select_prs(items: list[Any], dropped: dict[str, int]) -> list[PrRow]:
    """The merged, non-bot pull requests whose body states a reason (P9).

    Counts each rejection in ``dropped``: ``pr_incomplete`` (not merged or a field missing),
    ``pr_bot``, ``pr_housekeeping`` (a release or version bump title) and ``pr_no_reason``.
    """
    rows: list[PrRow] = []
    for item in items:
        fields = _complete(item) if isinstance(item, dict) else None
        if fields is None:
            dropped["pr_incomplete"] = dropped.get("pr_incomplete", 0) + 1
            continue
        number, title, body, url, day = fields
        if _is_bot(item):
            dropped["pr_bot"] = dropped.get("pr_bot", 0) + 1
        elif is_release_or_bump_subject(title):
            dropped["pr_housekeeping"] = dropped.get("pr_housekeeping", 0) + 1
        elif not (reason := extract_reason(title, body[:BODY_CAP])):
            dropped["pr_no_reason"] = dropped.get("pr_no_reason", 0) + 1
        else:
            rows.append(PrRow(number, title, body, url, day, _merge_sha(item), reason))
    return rows


def covering_numbers(rows: list[PrRow]) -> tuple[set[str], set[int]]:
    """The merge SHAs and numbers of the kept pull requests."""
    return {row.merge_sha for row in rows if row.merge_sha}, {row.number for row in rows}


def is_covered(sha: str, subjects: tuple[str, ...], shas: set[str], numbers: set[int]) -> bool:
    """Is this commit the one a kept pull request became (P10)?

    True when the SHA is a kept pull request's merge commit, or a subject ends ``(#N)`` for
    a kept pull request. ``subjects`` holds the subject as stored and the promoted subject.
    """
    if sha.lower() in shas:
        return True
    return any(trailing_pr_number(subject) in numbers for subject in subjects)
