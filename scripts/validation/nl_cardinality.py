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

A third form lives in structured data (`structured_count_claims`): a count word
and a plural noun inside a string value of a JSON or YAML object restate the
length of a sibling array in the same object ("these two PRs" beside a
three-item `pull_requests` list, PR #7311). The noun has to match the array's
key by token or initialism before the lengths are compared, so a count of
files never gets judged against a list of pull requests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

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
    rf"(?:all\s+|each\s+of\s+)?the\s+(?P<num>{_NUMBER})\s+"
    r"(?:[A-Za-z-]+\s+){0,2}?(?P<noun>[A-Za-z-]+s)\b(?P<tail>.*)$",
    re.IGNORECASE,
)
# A tail that opens a structure, a definition, or a link proves the reader can see the items.
_STRUCTURED_TAIL_RE = re.compile(
    r"[:(\[`]|\bin\s+(?:order|the\s+table)\b|\b(?:below|above)\b", re.IGNORECASE
)
# Text before the verb that still leaves it in imperative position: nothing, a Markdown
# marker, a clause boundary, a sequencing word, or a leading adverb. A subject or a modal
# ("Users can apply", "You may run") makes the sentence declarative.
_IMPERATIVE_PREFIX_RE = re.compile(
    r"^(?:\s*(?:[#>*+-]+|\d+[.)])?\s*(?:\*\*|__)?\s*(?:(?:always|first|then|next|also|just|now)\s+)?"
    r"|.*(?:[.!?:;]|,\s*(?:then|and|or)|\b(?:then|and|or))\s+(?:(?:always|first|also|just|now)\s+)?)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Claim:
    """One derived cardinality claim contradicted by its enumeration."""

    line: int
    text: str
    stated: int
    actual: int
    # The line with this claim's own number removed. Stored at detection so the fix
    # edits the flagged span, not a different count on the same line.
    simplified: str = ""


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


def _without_span(line: str, span: tuple[int, int]) -> str:
    """Return the line with the number at span removed, trimmed like Claim.text."""
    start, end = span
    return (line[:start] + line[end:].lstrip()).strip()


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
            fix = _without_span(line, match.span("num"))
            claims.append(Claim(index + 1, line.strip(), stated, actual, fix))
    return claims


def _identifier_count(lines: list[str], index: int, line: str) -> int:
    """Count unique IDs after a colon, including the next three lines."""
    paragraph = " ".join([line, *lines[index + 1 : index + 4]])
    enumeration = paragraph.split(":", 1)[1].split(". ", 1)[0]
    ids = re.findall(r"\b[A-Z]{2,}-\d+\b", enumeration)
    if len(ids) >= 2 and len(set(ids)) == len(ids):
        return len(ids)
    return 0


def _numbered_table_rows(lines: list[str], noun: str) -> int:
    """Return rows in the first numbered table whose header names ``noun``."""
    header_re = re.compile(rf"\|[^\n]*\b{noun}\b[^\n]*\|", re.I)
    row_re = re.compile(r"\|\s*\d+\s*\|")
    for start, header in enumerate(lines):
        if header_re.search(header) is None:
            continue
        rows = 0
        for row in lines[start + 1 :]:
            if not row.lstrip().startswith("|"):
                break
            if row_re.match(row):
                rows += 1
        if rows:
            return rows
    return 0


def _explicit_actual(lines: list[str], index: int, line: str, noun: str) -> int:
    """Return the structure size a records or generators claim can be checked against."""
    if noun == "records" and ":" in line:
        return _identifier_count(lines, index, line)
    if noun == "generators":
        return _numbered_table_rows(lines, "generator")
    return 0


def explicit_count_claims(text: str) -> list[Claim]:
    """Check stated counts against explicit identifier lists and ordered tables.

    Unlike bare imperatives, each result carries a contradictory structure.
    Wrapped identifier lists retain their original claim line.
    """
    claims = _contradicted_claims(text)
    lines = text.splitlines()
    fence: Fence | None = None
    pattern = re.compile(
        rf"\b(?P<num>{_NUMBER})\s+(?:[\w./-]+\.py\s+)?(?P<noun>records|generators)\b", re.I
    )
    for index, line in enumerate(lines):
        fence, delimiter = fence_step(line, fence)
        if delimiter or fence is not None:
            continue
        # A backticked script can qualify the counted generators.
        plain = re.sub(r"`[^`]+`\s+", "", line)
        match = pattern.search(plain)
        if not match or _is_contractual(plain[: match.start("num")]):
            continue
        actual = _explicit_actual(lines, index, line, match.group("noun").lower())
        stated = _number(match.group("num"))
        if actual >= 2 and stated != actual:
            claims.append(Claim(index + 1, line.strip(), stated, actual))
    return sorted({(c.line, c.stated, c.actual): c for c in claims}.values(), key=lambda c: c.line)


def _next_structure(lines: list[str], index: int) -> tuple[str, int]:
    """Classify what follows the claim line: ("table", 0), ("list", n), or ("none", 0)."""
    for line in lines[index + 1 :]:
        if not line.strip():
            continue
        if line.lstrip().startswith("|"):
            return "table", 0
        if _BULLET_RE.match(line):
            return "list", _bullet_items(lines, index)
        break
    return "none", 0


def bare_count_claims(text: str) -> list[Claim]:
    """Return imperatives that name a count with no enumeration to check it against.

    Retained: a non-imperative sentence, a contractual qualifier before the number, a
    structured tail (colon, parenthesis, link, backtick, "below"), a table row or a
    table on the next non-blank line, and a following list whose item count matches.
    A following list of a different size is reported with its real count in `actual`,
    on the same terms as the colon form (two or more items, stated under twice actual).
    With nothing to compare against, `actual` is 0.
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
        if not _IMPERATIVE_PREFIX_RE.match(line[: match.start("verb")]):
            continue
        if _is_contractual(line[: match.start("num")]):
            continue
        stated = _number(match.group("num"))
        kind, items = _next_structure(lines, index)
        if kind == "table" or (kind == "list" and not _list_contradicts(stated, items)):
            continue
        fix = _without_span(line, match.span("num"))
        claims.append(Claim(index + 1, line.strip(), stated, items, fix))
    return claims


def _list_contradicts(stated: int, items: int) -> bool:
    """Return True when a following list is a countable enumeration of a different size."""
    return items >= 2 and items != stated and stated < 2 * items


@dataclass(frozen=True)
class StructuredClaim:
    """One count word in a string value that its sibling array contradicts."""

    path: str
    line: int
    text: str
    stated: int
    actual: int
    array_key: str


# number, up to two modifier words, then a plural noun. No trailing structure is needed:
# the sibling array is the enumeration.
_STRUCTURED_CLAIM_RE = re.compile(
    rf"(?<![\w.-])(?P<num>{_NUMBER})\s+(?:[A-Za-z-]+\s+){{0,2}}?(?P<noun>[A-Za-z-]+s)\b",
    re.IGNORECASE,
)
_KEY_TOKEN_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def _singular(word: str) -> str:
    lowered = word.lower()
    return lowered[:-1] if lowered.endswith("s") and len(lowered) > 2 else lowered


def _noun_matches_key(noun: str, key: str) -> bool:
    """Return True when the noun names the key by token or by initialism.

    "files" matches `changed_files`; "PRs" matches `pull_requests` because p and r
    open its two tokens.
    """
    wanted = _singular(noun)
    tokens = [_singular(token) for token in _KEY_TOKEN_RE.findall(key)]
    if wanted in tokens:
        return True
    return len(tokens) > 1 and "".join(token[0] for token in tokens) == wanted


def _locate(lines: list[str], key: str, value: str) -> int:
    """Return the 1-based line that holds the string value, or 1 when it cannot be found."""
    needle = json.dumps(value, ensure_ascii=False)[1:-1][:30]
    holds = [i for i, line in enumerate(lines, 1) if needle and needle in line]
    keyed = [i for i in holds if key in lines[i - 1]]
    return (keyed or holds or [1])[0]


def _claims_in_string(value: str) -> list[tuple[int, str]]:
    """Return (stated, noun) for each non-contractual count in the string."""
    found = []
    for match in _STRUCTURED_CLAIM_RE.finditer(value):
        prefix = value[: match.start()]
        if _is_contractual(prefix) or _is_position_label(prefix, match.group("num")):
            continue
        found.append((_number(match.group("num")), match.group("noun")))
    return found


def _object_claims(obj: dict[str, Any], path: str, lines: list[str]) -> list[StructuredClaim]:
    arrays = {key: val for key, val in obj.items() if isinstance(val, list) and val}
    claims: list[StructuredClaim] = []
    for key, value in obj.items():
        if not isinstance(value, str):
            continue
        for stated, noun in _claims_in_string(value):
            matched = [name for name in arrays if _noun_matches_key(noun, name)]
            if len(matched) != 1 or len(arrays[matched[0]]) == stated:
                continue
            claims.append(
                StructuredClaim(
                    path=f"{path}.{key}" if path else key,
                    line=_locate(lines, key, value),
                    text=value,
                    stated=stated,
                    actual=len(arrays[matched[0]]),
                    array_key=matched[0],
                )
            )
    return claims


def _walk(node: object, path: str, lines: list[str]) -> list[StructuredClaim]:
    if isinstance(node, dict):
        found = _object_claims(node, path, lines)
        for key, child in node.items():
            found += _walk(child, f"{path}.{key}" if path else str(key), lines)
        return found
    if isinstance(node, list):
        return [c for i, child in enumerate(node) for c in _walk(child, f"{path}[{i}]", lines)]
    return []


def _parse_structured(text: str, kind: str) -> list[Any]:
    """Return the parsed documents, or none when the text does not parse as ``kind``."""
    if kind == "json":
        try:
            return [json.loads(text)]
        except ValueError:
            return []
    import yaml

    try:
        return list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return []


def structured_count_claims(text: str, kind: str) -> list[StructuredClaim]:
    """Return count words in JSON or YAML string values that a sibling array contradicts.

    ``kind`` is "json" or "yaml". Retained: a contractual qualifier before the number, an
    object with no matching sibling array, an empty array, and a noun that matches two
    arrays. With several arrays the noun picks one by token or initialism; with one array
    it still has to match, which is stricter than "compare the only list": "edits three
    files" beside a `pull_requests` list is not a claim about that list. A document that
    does not parse yields nothing, because syntax errors are other validators' job.
    """
    lines = text.splitlines()
    return [c for doc in _parse_structured(text, kind) for c in _walk(doc, "", lines)]
