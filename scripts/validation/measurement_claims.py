#!/usr/bin/env python3
"""Pure line classification for the measurement-anchoring gate (issue #5771).

A count that describes the current state of the repository is a measurement
of one commit. Once the tree moves, a reader cannot tell "still true" from
"was true once" unless the line names the commit or date it was taken at.
This module answers one question for one line of Markdown: does it state a
tree-state count, and does it carry an anchor. Git reads, scope, and the CLI
live in ``check_measurement_anchoring.py``.

The trigger is deliberately narrow. A loose "integer plus noun" scan over
the tracked Markdown reported 1,882 lines in the live governance trees at
``55ec6212c`` (2026-09-15), and a hand-classified sample of 25 held roughly
one genuine claim. A count is a tree-state claim here only when the line
qualifies it as one:

* ``N tracked <noun>``;
* ``N <noun> under|in|inside `<path>```, or ``N in `<dir>/```;
* ``N <noun> ... in this repository | on main | in the tree``.

Policy thresholds ("Max 15 skills", "stay under 60 lines"), fixed
constants, and ``#123`` issue numbers are not claims about current state.
"""

from __future__ import annotations

import re

IGNORE_MARKER = "measurement-anchor: ignore"
_IGNORE_WITH_REASON = re.compile(re.escape(IGNORE_MARKER) + r"\s+--\s+\S")

_NUM = r"(?<![\w#./-])~?\d+(?:,\d{3})*k?(?![\w-]|\.\d)"
_WORD = r"[A-Za-z][\w-]*"
# A count noun is plural: "109 skills", not "step 0.5 lives" or "exit 0 green".
_PLURAL = r"[A-Za-z][\w-]*s\b"
_NOUN_PHRASE = rf"(?:{_WORD}\s+){{0,2}}{_PLURAL}"

_TRACKED = re.compile(rf"{_NUM}\s+tracked\s+{_PLURAL}", re.IGNORECASE)
_PATH_NOUN = re.compile(
    rf"{_NUM}\s+{_NOUN_PHRASE}\s+(?:under|in|inside)\s+`[^`\s]*/[^`\s]*`", re.IGNORECASE
)
_PATH_BARE = re.compile(rf"{_NUM}\s+(?:under|in|inside)\s+`[^`\s]*/`", re.IGNORECASE)
_REPO_QUALIFIER = r"(?:in\s+this\s+(?:repository|repo)|on\s+`?main`?|in\s+the\s+tree)\b"
# Braces are doubled: the gap bound sits inside an f-string, where a bare
# {0,60} would format as the tuple "(0, 60)" instead of a quantifier.
_REPO_NOUN = re.compile(
    rf"{_NUM}\s+{_NOUN_PHRASE}\b[^.;:|\x22\n]{{0,60}}?\b{_REPO_QUALIFIER}",
    re.IGNORECASE,
)
_CLAIM_SHAPES = (_TRACKED, _PATH_NOUN, _PATH_BARE, _REPO_NOUN)

# A label, not a count: "Step 0 heading", "exit 1 red", "row 3 in `path/`".
_LABEL_LEAD = re.compile(
    r"\b(?:steps?|sections?|phases?|stages?|tiers?|levels?|gates?|exit(?:\s+codes?)?|codes?|"
    r"items?|rows?|rules?|must|milestones?|tasks?|ac|req|adr|issues?|prs?|pull|lines?|"
    r"pages?|chapters?|figures?|tables?|versions?)\s+$",
    re.IGNORECASE,
)

# A bound, not a measurement: the words just before the number say so.
_THRESHOLD_LEAD = re.compile(
    r"\b(?:max(?:imum)?|min(?:imum)?|at\s+most|at\s+least|up\s+to|limit|cap|capped\s+at|"
    r"under|over|below|above|fewer\s+than|more\s+than|no\s+more\s+than|less\s+than|"
    r"exceed(?:s|ed|ing)?|within)\s+(?:of\s+)?$",
    re.IGNORECASE,
)

_HEX_TOKEN = re.compile(r"(?<![\w-])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![\w-])")
_ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
_SEMVER_TAG = re.compile(r"(?<![\w.])v?\d+\.\d+\.\d+(?![\w.])")

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_FENCE = re.compile(r"^\s{0,3}(?P<mark>`{3,}|~{3,})")


def fenced_line_numbers(lines: list[str]) -> set[int]:
    """Return the 1-based numbers of lines inside (or delimiting) code fences."""
    fenced: set[int] = set()
    open_mark: str | None = None
    for number, text in enumerate(lines, 1):
        match = _FENCE.match(text)
        if open_mark is None:
            if match:
                open_mark = match.group("mark")
                fenced.add(number)
            continue
        fenced.add(number)
        closes = (
            match
            and match.group("mark")[0] == open_mark[0]
            and len(match.group("mark")) >= len(open_mark)
            and not text.strip().strip(open_mark[0])
        )
        if closes:
            open_mark = None
    return fenced


def is_heading(text: str) -> bool:
    """Return whether the line is an ATX heading."""
    return bool(_HEADING.match(text))


def has_anchor(text: str) -> bool:
    """Return whether the line names a commit, an ISO date, or a version tag."""
    return bool(_HEX_TOKEN.search(text) or _ISO_DATE.search(text) or _SEMVER_TAG.search(text))


def tree_state_claims(text: str) -> list[str]:
    """Return each tree-state count phrase on the line, thresholds excluded."""
    found: list[str] = []
    for shape in _CLAIM_SHAPES:
        for match in shape.finditer(text):
            lead = text[: match.start()]
            if _THRESHOLD_LEAD.search(lead) or _LABEL_LEAD.search(lead):
                continue
            if match.group(0) not in found:
                found.append(match.group(0))
    return found


def has_reasoned_ignore(lines: list[str] | None, line_number: int, text: str) -> bool:
    """Return whether the line or the one above carries a reasoned ignore marker."""
    if _IGNORE_WITH_REASON.search(text):
        return True
    if lines is None:
        return False
    previous = line_number - 2
    return 0 <= previous < len(lines) and bool(_IGNORE_WITH_REASON.search(lines[previous]))


def unanchored_claims(text: str) -> list[str]:
    """Return the tree-state counts on the line when the line has no anchor."""
    claims = tree_state_claims(text)
    if not claims or has_anchor(text):
        return []
    return claims
