#!/usr/bin/env python3
"""Pure report logic for backlog_provenance.py (issue #5702, epic #5698).

No network, no argparse, no gh. Parses REST issue records, buckets them by
recorded ``source:*`` label, applies two labeled heuristics, and renders the
report. ``backlog_provenance.py`` owns the GitHub I/O and the CLI.

What the numbers mean:
    * ``source:human`` and ``source:agent`` labels are recorded provenance
      (owned by #5700). They are not independently verified human selection.
      Provenance is never inferred from author, timing, title, or approval.
    * Buckets are mutually exclusive: ``human-only``, ``agent-only``,
      ``conflict`` (both labels), ``unknown`` (neither label).
    * Machinery share and bursts are heuristics. They are not causal
      attribution, a quality judgment, or a closure recommendation.

Burst rule (``find_bursts`` is a standalone function, intended for reuse by
#5704, which does not import it yet): per login, sort creation times, then
greedily start a burst at the earliest unassigned issue and take every later
issue within 10 minutes of that start. A group of 3 or more issues is a burst
and each issue belongs to at most one burst.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

BURST_MINIMUM = 3
BURST_WINDOW = timedelta(minutes=10)
HUMAN_LABEL = "source:human"
AGENT_LABEL = "source:agent"
MACHINERY_LABEL = "area-validation"
MACHINERY_TERMS = (
    "validation",
    "validator",
    "ratchet",
    "hook",
    "lefthook",
    "adr",
    "pre_pr",
    "pre-push",
    "pr-autofix",
    "memory",
    "gate",
    "drift",
)
# Whole-word match with an optional plural, so "adr" does not match "address",
# "hooks" still counts, and hyphen or dot neighbours ("ADR-042", "hook-based")
# still match. Canonical rule text: issue #5702 step 4, "matches
# any of validation, validator, ratchet, hook, lefthook, adr, pre_pr, pre-push,
# pr-autofix, memory, gate, drift, or if its labels include area-validation".
# Stricter than canonical: the issue does not say word-bounded; the term list
# pairs "hook" with "lefthook" and "validation" with "validator", which only
# makes sense when matching is word-bounded.
_MACHINERY_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in MACHINERY_TERMS) + r")s?\b",
    re.IGNORECASE,
)
BUCKETS = ("human-only", "agent-only", "conflict", "unknown")
LIMITATIONS = (
    "Labels record provenance; they do not verify who selected the work.",
    "Machinery share is a title and label heuristic, not causal attribution.",
    "Bursts are a timing heuristic, not evidence of agent authorship.",
    "The report does not show reduced unwanted work or token-cost savings.",
)


class ReportError(Exception):
    """A failure that maps to an ADR-035 exit code and an envelope error type."""

    def __init__(self, message: str, exit_code: int, error_type: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.error_type = error_type


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    login: str
    created_at: datetime
    labels: frozenset[str]


@dataclass
class ReadStats:
    pages: int = 0
    records_fetched: int = 0
    pull_requests_excluded: int = 0
    duplicates_dropped: int = 0
    out_of_window_excluded: int = 0


@dataclass
class Backlog:
    issues: list[Issue] = field(default_factory=list)
    stats: ReadStats = field(default_factory=ReadStats)


def parse_timestamp(value: object) -> datetime:
    """Parse a GitHub ISO-8601 UTC timestamp, or raise ReportError (exit 3)."""
    if not isinstance(value, str) or not value:
        raise ReportError(f"Malformed created_at value: {value!r}", 3, "ApiError")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReportError(f"Malformed created_at value: {value!r} ({exc})", 3, "ApiError") from exc
    if parsed.tzinfo is None:
        raise ReportError(f"created_at has no timezone: {value!r}", 3, "ApiError")
    return parsed.astimezone(timezone.utc)


def record_number(record: object) -> int:
    """Return a record's integer issue or pull request number, or raise (exit 3)."""
    if not isinstance(record, dict):
        raise ReportError(f"Malformed issue record: {type(record).__name__}", 3, "ApiError")
    number = record.get("number")
    if isinstance(number, bool) or not isinstance(number, int):
        raise ReportError(f"Issue record has no integer number: {number!r}", 3, "ApiError")
    return number


def parse_record(record: object) -> Issue:
    """Build an Issue from one REST issue record, or raise ReportError (exit 3)."""
    if not isinstance(record, dict):
        raise ReportError(f"Malformed issue record: {type(record).__name__}", 3, "ApiError")
    number = record_number(record)
    return Issue(
        number=number,
        title=str(record.get("title") or ""),
        login=_login(record, number),
        created_at=parse_timestamp(record.get("created_at")),
        labels=_label_names(record, number),
    )


def _label_names(record: dict[str, Any], number: int) -> frozenset[str]:
    """Lowercased label names. The issue schema allows string or object items."""
    labels = record.get("labels")
    if not isinstance(labels, list):
        raise ReportError(f"Issue {number} has malformed labels: {labels!r}", 3, "ApiError")
    names: set[str] = set()
    for label in labels:
        if isinstance(label, str):
            names.add(label.lower())
        elif isinstance(label, dict):
            names.add(str(label.get("name", "")).lower())
        else:
            raise ReportError(f"Issue {number} has malformed labels: {labels!r}", 3, "ApiError")
    return frozenset(names)


def _login(record: dict[str, Any], number: int) -> str:
    user = record.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    if not isinstance(login, str) or not login:
        raise ReportError(f"Issue {number} has no author login", 3, "ApiError")
    return login


def classify_provenance(issue: Issue) -> str:
    """Return the mutually exclusive provenance bucket for one issue."""
    human = HUMAN_LABEL in issue.labels
    agent = AGENT_LABEL in issue.labels
    if human and agent:
        return "conflict"
    if human:
        return "human-only"
    if agent:
        return "agent-only"
    return "unknown"


def is_machinery(issue: Issue) -> bool:
    """Heuristic: a machinery term in the title, or the area-validation label."""
    return MACHINERY_LABEL in issue.labels or _MACHINERY_RE.search(issue.title) is not None


def find_bursts(issues: list[Issue]) -> list[list[int]]:
    """Return burst groups as sorted issue numbers (see module docstring)."""
    by_login: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        by_login[issue.login].append(issue)
    bursts: list[list[int]] = []
    for login in sorted(by_login):
        bursts.extend(_bursts_for_login(by_login[login]))
    return sorted(bursts)


def _bursts_for_login(issues: list[Issue]) -> list[list[int]]:
    ordered = sorted(issues, key=lambda item: (item.created_at, item.number))
    bursts: list[list[int]] = []
    index = 0
    while index < len(ordered):
        start = ordered[index].created_at
        end = index
        while end + 1 < len(ordered) and ordered[end + 1].created_at - start <= BURST_WINDOW:
            end += 1
        group = ordered[index : end + 1]
        if len(group) >= BURST_MINIMUM:
            bursts.append(sorted(item.number for item in group))
        index = end + 1
    return bursts


def share(count: int, total: int) -> float | None:
    """Ratio rounded to 4 places, or None when the total is zero."""
    return None if total == 0 else round(count / total, 4)


def build_report(
    backlog: Backlog,
    owner: str,
    repo: str,
    endpoint: str,
    start: datetime,
    end: datetime,
    retrieved_at: datetime,
) -> dict[str, Any]:
    """Assemble the report. Every issue lands in exactly one provenance bucket."""
    issues = sorted(backlog.issues, key=lambda item: item.number)
    total = len(issues)
    buckets: dict[str, list[int]] = {name: [] for name in BUCKETS}
    for issue in issues:
        buckets[classify_provenance(issue)].append(issue.number)
    machinery = [issue.number for issue in issues if is_machinery(issue)]
    bursts = find_bursts(issues)
    return {
        "repository": f"{owner}/{repo}",
        "window": {
            "start": _iso(start),
            "end": _iso(end),
            "boundaries": "created_at >= start and created_at < end",
        },
        "query": f"GET {endpoint} (pages until empty; created_at filtered client-side)",
        "retrieved_at": _iso(retrieved_at),
        "completeness": {"complete": True, **vars(backlog.stats)},
        "total": total,
        "provenance": {
            name: {
                "count": len(numbers),
                "share": share(len(numbers), total),
                "issues": numbers,
            }
            for name, numbers in buckets.items()
        },
        "machinery_heuristic": {
            "count": len(machinery),
            "share": share(len(machinery), total),
            "issues": machinery,
            "rule": "title has a machinery term as a whole word, or label area-validation",
        },
        "bursts": {
            "count": len(bursts),
            "issue_count": sum(len(group) for group in bursts),
            "groups": bursts,
            "rule": (
                f"{BURST_MINIMUM}+ issues by one login within "
                f"{int(BURST_WINDOW.total_seconds() // 60)} minutes of the burst's first issue"
            ),
        },
        "limitations": list(LIMITATIONS),
    }


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: dict[str, Any]) -> str:
    """Render the report as Markdown. Empty ratios print N/A, never 0."""
    window = report["window"]
    done = report["completeness"]
    lines = [
        "# Backlog Provenance",
        "",
        f"Repository: {report['repository']}",
        f"Window (UTC): {window['start']} to {window['end']} ({window['boundaries']})",
        f"Retrieved: {report['retrieved_at']}",
        f"Query: {report['query']}",
        (
            f"Read complete: {done['pages']} page(s), {done['records_fetched']} record(s), "
            f"{done['pull_requests_excluded']} pull request(s) excluded, "
            f"{done['duplicates_dropped']} duplicate(s) dropped, "
            f"{done['out_of_window_excluded']} outside the window"
        ),
        "",
        f"New issues in window: {report['total']}",
        "",
        "| Provenance | Count | Share |",
        "|---|---|---|",
    ]
    for name in BUCKETS:
        entry = report["provenance"][name]
        lines.append(f"| {name} | {entry['count']} | {_percent(entry['share'])} |")
    machinery = report["machinery_heuristic"]
    bursts = report["bursts"]
    lines += [
        "",
        f"Machinery share (heuristic): {machinery['count']} ({_percent(machinery['share'])}); "
        f"{machinery['rule']}",
        f"Bursts (heuristic): {bursts['count']} burst(s) covering {bursts['issue_count']} "
        f"issue(s); {bursts['rule']}",
        "",
        "Limitations:",
        *[f"- {text}" for text in report["limitations"]],
        "",
    ]
    return "\n".join(lines)
