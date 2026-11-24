"""Added-line ADR-073 last-updated checks for the advisory documentation gate.

The lifecycle checker owns a frozen tree baseline, without added-line scope.
This helper checks changes against their commit date through the docs gate.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# The per-file mypy gate sets MYPYPATH to this directory. One file under two
# names fails the ratchet. Claims stay a bare sibling import. The frontmatter
# parser stays on the package path so its SafeLoader override still applies.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import doc_date_claims as claims  # noqa: E402
import yaml  # noqa: E402

from scripts.hook_utilities.frontmatter_block import parse_frontmatter  # noqa: E402

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
    parsed = parse_frontmatter("\n".join(lines), yaml)
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
    if date_line is None or claims.has_reasoned_ignore(lines, date_line, lines[date_line - 1]):
        return None
    proving: list[tuple[date, int]] = []
    fallback: list[int] = []
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
        if number not in added or claims.has_reasoned_ignore(lines, number, text):
            continue
        dates = (
            claims.dates_on_line(text) if decision_level or heading or _MARKER.search(text) else []
        )
        # A later deadline is not the day the record changed. One extra day
        # covers a commit timestamp that falls on the previous UTC day.
        # An older citation does not record this edit. Month-only text has no day.
        latest = commit_date + timedelta(days=1)
        kept = [d.value for d in dates if not d.month_only and d.value <= latest]
        proves_update = [value for value in kept if value >= updated]
        decision_edit = decision_level and text.strip() and not heading
        if proves_update:
            proving.extend((value, number) for value in proves_update)
        elif decision_edit or (bool(dates) and not kept):
            fallback.append(number)
    candidates = proving or [(commit_date, number) for number in fallback]
    if not candidates:
        return None
    newest, other = max(candidates, key=lambda candidate: candidate[0])
    return AdrProblem(date_line, other, newest) if updated < newest else None
