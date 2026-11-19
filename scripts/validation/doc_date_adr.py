"""Added-line ADR-073 last-updated checks for the advisory documentation gate.

The lifecycle checker owns a frozen tree baseline, without added-line scope.
This helper checks changes against their commit date through the docs gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from scripts.validation.doc_date_claims import dates_on_line, has_reasoned_ignore
from scripts.validation.frontmatter_contract import parse_frontmatter

RULE_ADR = "adr-date"
_ADR_PATH = re.compile(r"^(?:\.project-toolkit|\.agents)/architecture/ADR-\d+[^/]*\.md$")
_DATE_FIELD = re.compile(r"^date\s*:")
_HEADING = re.compile(r"^(#{1,6})\s+(.+)")
_DECISION = re.compile(r"^decisions?\b", re.IGNORECASE)
_MARKER = re.compile(r"\bamend(?:ed|ment)\b|^\s*(?:#{1,6}\s+|\*\*)?status\b", re.IGNORECASE)


@dataclass(frozen=True)
class AdrProblem:
    """The old frontmatter date and its newer body evidence."""

    date_line: int
    other_line: int
    suggested: date


def adr_problem(
    path: str, lines: list[str], added: set[int], fenced: set[int], commit_date: date
) -> AdrProblem | None:
    """Find the newest added amendment or changed Decision section date."""
    if not _ADR_PATH.match(path):
        return None
    parsed = parse_frontmatter("\n".join(lines))
    if not parsed.ok or not parsed.metadata:
        return None
    raw_date = parsed.metadata.get("date")
    try:
        updated = date.fromisoformat(str(raw_date))
    except ValueError:
        return None
    body_start = len(lines) - len(parsed.body.split("\n")) + 1
    date_line = next(
        (n for n, text in enumerate(lines[: body_start - 1], 1) if _DATE_FIELD.match(text)), None
    )
    if date_line is None or has_reasoned_ignore(lines, date_line, lines[date_line - 1]):
        return None
    dated: list[tuple[date, int]] = []
    undated: list[int] = []
    decision_level = 0
    for number, text in enumerate(lines, 1):
        if number < body_start or number in fenced:
            continue
        heading = _HEADING.match(text)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            if _DECISION.match(title):
                decision_level = level
            elif decision_level and level <= decision_level:
                decision_level = 0
        if number not in added or has_reasoned_ignore(lines, number, text):
            continue
        dates = dates_on_line(text) if decision_level or heading or _MARKER.search(text) else []
        if dates:
            dated.extend((d.value, number) for d in dates if not d.month_only)
        elif decision_level and text.strip() and not heading:
            undated.append(number)
    candidates = dated or [(commit_date, n) for n in undated]
    if not candidates:
        return None
    newest, other = max(candidates, key=lambda candidate: candidate[0])
    return AdrProblem(date_line, other, newest) if updated < newest else None
