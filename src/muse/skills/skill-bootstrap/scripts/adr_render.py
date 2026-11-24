# Port of aligndottech/align-cli at commit 8d758e9899677b61442b08ffda74b74887bfc42a
# Ported upstream files:
#   src/lib/adr-writer.ts          (renderAdr and slug, lines 52-84; the section kinds are in
#                                   adr_shape.py)
# Sibling ports: adr_shape.py, adr_reason.py, adr_commits.py, adr_docs.py, adr_locate.py,
# adr_render.py, adr_scan.py, bootstrap_adr.py.
# MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align
"""Render one drafted ADR from a scan candidate, in the folder style ``adr_locate`` reads.

Pure functions over strings. Standard library only. Departures from the upstream source,
each pinned by a test:

- Status is the caller's (``Proposed`` by default), never ``Accepted``.
- Headings follow the newest ADR of the folder, and a heading the source does not fill says
  ``Not recorded in the source.``
- Every source field is one line, and a title that starts with Markdown syntax is escaped,
  so text from a commit or a scan file cannot add structure to the draft.
- A commit or pull request title loses its ``type(scope)!:`` prefix and trailing ``(#N)``.

Regex notes: see the module docstring of ``adr_shape.py``; they apply to every module here.
"""

from __future__ import annotations

import re
from typing import Any

from adr_commits import iso_day, one_line, sanitize
from adr_locate import Style, render_h1
from adr_shape import section_kind

__all__ = ["NOT_RECORDED", "NO_REASON", "adr_title", "clean_source", "render"]

NOT_RECORDED = "Not recorded in the source."
NO_REASON = "The source states no reason."
_TYPE_PREFIX = re.compile(r"\A[a-z]+(?:\([^)]*\))?!?:[ \t]+", re.IGNORECASE | re.ASCII)
_PR_SUFFIX = re.compile(r"\(#[0-9]+\)\Z", re.ASCII)
_URL = re.compile(r"https://[^\s<>`\"']+\Z", re.ASCII)
_SHA = re.compile(r"[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64}", re.ASCII)
# A mark that starts a heading, quote, list, fence, rule or table, or a list number.
_MD_LEAD = re.compile(r"[#>+*=`~|-]|[0-9]+[.)](?=[ \t]|\Z)", re.ASCII)


def clean_source(source: object) -> dict[str, Any]:
    """The source fields the draft quotes, each string on one line.

    A ``sha`` that is not 40 or 64 hex digits is dropped, and so is a ``url`` or ``pr_url`` that
    is not one ``https://`` word, so no source field can add a line to the draft.
    """
    cleaned: dict[str, Any] = {}
    for key, value in (source if isinstance(source, dict) else {}).items():
        text = one_line(sanitize(value)) if isinstance(value, str) else value
        pattern = {"sha": _SHA, "url": _URL, "pr_url": _URL}.get(key)
        if pattern is None or (isinstance(text, str) and pattern.fullmatch(text)):
            cleaned[key] = text
    return cleaned


def _plain(text: str) -> str:
    """One line of ``text`` that cannot start Markdown structure: a backslash goes in front of a
    leading mark, so ``## x`` or a code fence shows as text."""
    return f"\\{text}" if _MD_LEAD.match(text) else text


def _link(candidate: dict[str, Any]) -> str:
    source = candidate.get("source")
    source = source if isinstance(source, dict) else {}
    url = source.get("url")
    if isinstance(url, str) and _URL.fullmatch(url):
        return url
    if candidate["kind"] == "decision-log":
        entry = str(source.get("entry_id") or "")
        return f"{source.get('file') or ''} (entry {entry})".strip()
    sha = source.get("sha")
    return f"commit {sha}" if isinstance(sha, str) and sha else ""


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def _context(candidate: dict[str, Any]) -> str:
    reason = candidate.get("reason")
    excerpt = (candidate.get("excerpt") or "").strip()
    noun = {"pr": "pull request", "decision-log": "decision log entry"}.get(
        candidate["kind"], "commit"
    )
    parts = [f"The reason given at the time: {reason}" if reason else NO_REASON]
    if excerpt:
        parts.append(f"From the source {noun}:\n\n{_quote(excerpt)}")
    return "\n\n".join(parts)


def _decision(candidate: dict[str, Any]) -> str:
    link = _link(candidate)
    return f"{_plain(candidate['title'])}\n\n" + (
        f"Decided in {link}" if link else "Where it was decided was not recorded."
    )


def render(style: Style, number: int, candidate: dict[str, Any], status: str) -> str:
    """The ADR text. Headings come from ``style``; an unfilled heading says so.

    The candidate's text fields must already be cleaned by the caller.
    """
    day = iso_day(candidate.get("date"))
    kinds = [section_kind(heading) for heading in style.headings]
    lines = [render_h1(style.h1_form, number, candidate["title"]), ""]
    header = ([f"Date: {day}"] if day and "date" not in kinds else []) + (
        [f"Status: {status}"] if "status" not in kinds else []
    )
    if header:
        lines += [*header, ""]
    filled = {
        "status": status,
        "date": day or NOT_RECORDED,
        "context": _context(candidate),
        "decision": _decision(candidate),
    }
    # The source text must always land somewhere: a folder whose newest ADR has no context or
    # decision heading gets one appended. Only the first heading of each kind is filled.
    sections = list(zip(style.headings, kinds, strict=True))
    sections += [(name.capitalize(), name) for name in ("context", "decision") if name not in kinds]
    used: set[str] = set()
    for heading, kind in sections:
        text = filled.get(kind, NOT_RECORDED) if kind not in used else NOT_RECORDED
        used.add(kind)
        lines += [f"## {heading}", "", text, ""]
    return "\n".join(lines)


def adr_title(kind: str, title: str) -> str:
    """The ADR title for a source title: a commit or pull request loses its conventional
    ``type(scope)!:`` prefix and its trailing ``(#N)``. Upstream keeps both."""
    if kind == "decision-log":
        return title
    cleaned = _PR_SUFFIX.sub("", _TYPE_PREFIX.sub("", title, count=1)).strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else title
