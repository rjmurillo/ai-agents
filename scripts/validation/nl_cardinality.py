"""Detect derived cardinality claims that an adjacent structure contradicts.

A phrase like "the three filters" followed by a list of four filters is
duplicated mutable state: the number restates a fact the list already holds,
and the two drift apart. This module flags only the high-confidence case, where
a number word and a plural noun are directly followed by an enumeration of a
different size. A count with no nearby structure is left alone, because nothing
proves it wrong.

A second, narrower form is also flagged: an imperative that names a bare count
("Run the three filters.") with no enumeration after it. The number then restates
a fact held elsewhere, and nothing on the page proves it right. Only an imperative
verb opens this form, because "the two facts below" and "the three programs" often
refer to a structure the reader can see. Measured repo-wide, that restriction keeps
the form to a handful of lines; an unrestricted "the N nouns" match hits ~160.

An explicit contractual form ("exactly three", "at least two", "no more than
four") is retained: the number is the requirement, not a copy of a list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NUMBER_WORDS: dict[str, int] = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

_NUMBER = "|".join([*NUMBER_WORDS, r"\d{1,2}"])

# number, up to two modifier words, one plural noun, then a colon or opening paren.
# A run of three or more backticks or tildes, then the rest of the line.
_FENCE_RE = re.compile(r"^\s*(?P<run>`{3,}|~{3,})(?P<rest>.*)$")

Fence = tuple[str, int]


def fence_step(line: str, open_fence: Fence | None) -> tuple[Fence | None, bool]:
    """Advance CommonMark fence state by one line.

    Returns the new open fence (char, length) or None, and whether the line is a fence
    line. A closer needs the same char, at least the opener's length, and only trailing
    whitespace. A backtick opener may not carry a backtick in its info string. Shared by
    the cardinality scan and the duplicate-block scan so the two cannot drift.
    """
    match = _FENCE_RE.match(line)
    if match is None:
        return open_fence, False
    run, rest = match.group("run"), match.group("rest")
    if open_fence is None:
        if run[0] == "`" and "`" in rest:
            return None, False
        return (run[0], len(run)), True
    char, length = open_fence
    if run[0] == char and len(run) >= length and not rest.strip():
        return None, True
    return open_fence, True


_CLAIM_RE = re.compile(
    rf"(?<![\w.-])(?P<num>{_NUMBER})\s+(?:[A-Za-z-]+\s+){{0,2}}?(?P<noun>[A-Za-z-]+s)\s*"
    r"(?P<open>[:(])\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

_CONTRACT_RE = re.compile(
    r"\b(exactly|at least|at most|no more than|no fewer than|only|up to|minimum of|"
    r"maximum of|a maximum|a minimum|more than|fewer than|fewer|more)\s+"
    r"(?:of\s+)?(?:the\s+)?$",
    re.IGNORECASE,
)

# A digit after one of these words names a position ("Phase 1"), not a quantity.
_LABEL_RE = re.compile(
    r"\b(phase|step|stage|section|part|tier|gate|round|rule|item|issue|level|chapter)\s+$",
    re.IGNORECASE,
)

# An item longer than this is prose, not an enumerated name, so the count is unsafe to judge.
MAX_ITEM_WORDS = 5
_BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+\S")
_ITEM_SPLIT_RE = re.compile(r"\s*,\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+", re.IGNORECASE)


# An imperative verb, an optional quantifier, then "the N [modifiers] plural-noun".
_BARE_RE = re.compile(
    rf"\b(?P<verb>run|apply|use|check|invoke|execute|call|pass|dispatch|answer|clear)\s+"
    rf"(?:all\s+|each\s+of\s+)?the\s+(?P<num>{'|'.join(NUMBER_WORDS)})\s+"
    r"(?:[A-Za-z-]+\s+){0,2}?(?P<noun>[A-Za-z-]+s)\b(?P<tail>.*)$",
    re.IGNORECASE,
)
# A tail that opens a structure, a definition, or a link proves the reader can see the items.
_STRUCTURED_TAIL_RE = re.compile(r"[:(\[`]|\bin\s+(?:order|the\s+table)\b|\b(?:below|above)\b")


@dataclass(frozen=True)
class Claim:
    """One derived cardinality claim contradicted by its enumeration."""

    line: int
    text: str
    stated: int
    actual: int


def _number(token: str) -> int:
    """Return the integer a number token names."""
    lowered = token.lower()
    return NUMBER_WORDS[lowered] if lowered in NUMBER_WORDS else int(lowered)


def _inline_items(rest: str, opener: str) -> int:
    """Count the items in an inline enumeration after the claim."""
    body = rest.rstrip()
    if body.endswith(",") or (opener == ":" and "(" in body):
        return 0
    if opener == "(":
        end = body.find(")")
        if end < 0:
            return 0
        body = body[:end]
        if any(ch.isdigit() for ch in body):
            return 0
    else:
        body = body.rstrip(".;")
    body = body.strip()
    if not body:
        return 0
    parts = [part for part in _ITEM_SPLIT_RE.split(body) if part.strip()]
    if any(len(part.split()) > MAX_ITEM_WORDS or part.count("`") % 2 for part in parts):
        return 0
    # A fragment carrying a number is a subtotal ("24 ... and 6 ..."), not an item.
    if any(any(ch.isdigit() for ch in part) for part in parts):
        return 0
    return len(parts)


def _bullet_items(lines: list[str], start: int) -> int:
    """Count same-level list items directly under a claim line."""
    first = None
    count = 0
    for line in lines[start + 1 :]:
        if not line.strip():
            if count:
                break
            continue
        match = _BULLET_RE.match(line)
        if not match:
            # A wrapped item continues on a line indented past its bullet.
            if first is not None and len(line) - len(line.lstrip()) > first:
                continue
            break
        indent = len(match.group(1))
        if first is None:
            first = indent
        if indent == first:
            count += 1
        elif indent < first:
            break
    return count


def _is_position_label(prefix: str, number: str) -> bool:
    """Return True when a digit is an ordinal label such as "Phase 1", not a count."""
    return number.isdigit() and bool(_LABEL_RE.search(prefix))


def _is_contractual(prefix: str) -> bool:
    """Return True when the number carries an explicit contract qualifier."""
    return bool(_CONTRACT_RE.search(prefix))


def derived_count_claims(text: str) -> list[Claim]:
    """Return every derived count: contradicted by its enumeration, or bare with none."""
    return sorted([*_contradicted_claims(text), *bare_count_claims(text)], key=lambda c: c.line)


def _contradicted_claims(text: str) -> list[Claim]:
    """Return every claim whose stated count differs from its enumeration."""
    lines = text.splitlines()
    claims: list[Claim] = []
    fence: Fence | None = None
    for index, line in enumerate(lines):
        fence, is_fence_line = fence_step(line, fence)
        if is_fence_line:
            continue
        if fence is not None:
            continue
        match = _CLAIM_RE.search(line)
        if line.lstrip().startswith("|") or not match:
            continue
        prefix = line[: match.start()]
        if _is_contractual(prefix) or _is_position_label(prefix, match.group("num")):
            continue
        stated = _number(match.group("num"))
        rest = match.group("rest")
        actual = _inline_items(rest, match.group("open")) if rest.strip() else 0
        if match.group("open") == ":" and not rest.strip():
            actual = _bullet_items(lines, index)
        # Far fewer items than the stated count reads as a partial example list,
        # not an exhaustive enumeration, so decline to judge it.
        if actual >= 2 and actual != stated and stated < 2 * actual:
            claims.append(Claim(index + 1, line.strip(), stated, actual))
    return claims


def _followed_by_structure(lines: list[str], index: int) -> bool:
    """Return True when the next non-blank line starts a list or table."""
    for line in lines[index + 1 :]:
        if line.strip():
            return bool(_BULLET_RE.match(line)) or line.lstrip().startswith("|")
    return False


def bare_count_claims(text: str) -> list[Claim]:
    """Return imperatives that name a count with no enumeration to check it against.

    Retained: a contractual qualifier before the number, a structured tail (colon,
    parenthesis, link, backtick, "below"), a table row, and a list or table on the next
    non-blank line. `actual` is 0 because there is nothing to compare against.
    """
    lines = text.splitlines()
    claims: list[Claim] = []
    fence: Fence | None = None
    for index, line in enumerate(lines):
        fence, is_fence_line = fence_step(line, fence)
        if is_fence_line or fence is not None or line.lstrip().startswith("|"):
            continue
        match = _BARE_RE.search(line)
        if match is None or _STRUCTURED_TAIL_RE.search(match.group("tail")):
            continue
        if _is_contractual(line[: match.start("num")]) or _followed_by_structure(lines, index):
            continue
        claims.append(Claim(index + 1, line.strip(), _number(match.group("num")), 0))
    return claims


def simplify(claim_text: str) -> str:
    """Return the claim with the derived number removed.

    Uses the detector's own patterns, so the span removed is the span flagged.
    """
    match = _CLAIM_RE.search(claim_text) or _BARE_RE.search(claim_text)
    if match is None:
        return claim_text
    start, end = match.span("num")
    tail = claim_text[end:].lstrip()
    return claim_text[:start] + tail
