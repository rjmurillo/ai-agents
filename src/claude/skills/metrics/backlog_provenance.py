#!/usr/bin/env python3
"""Backlog provenance report for new issues (issue #5702, epic #5698).

Read-only diagnostic. It reports how many issues were created in an explicit
UTC interval, split by recorded ``source:*`` label, plus two labeled
heuristics (machinery titles and creation bursts). It is not a productivity
score and it never files, labels, or closes an issue.

What the numbers mean:
    * ``source:human`` and ``source:agent`` labels are recorded provenance
      (owned by #5700). They are not independently verified human selection.
      Provenance is never inferred from author, timing, title, or approval.
    * Buckets are mutually exclusive: ``human-only``, ``agent-only``,
      ``conflict`` (both labels), ``unknown`` (neither label).
    * Machinery share and bursts are heuristics. They are not causal
      attribution, a quality judgment, or a closure recommendation.

Completeness: the REST issue list is read page by page until an empty page.
Any failed or malformed page aborts the run with exit 3. Partial counts are
never published as complete. Pull-request records are excluded and records are
deduplicated by immutable issue number.

Burst rule (``find_bursts`` is a standalone function, intended for reuse by
#5704, which does not import it yet): per login, sort
creation times, then greedily start a burst at the earliest unassigned issue
and take every later issue within 10 minutes of that start. A group of 3 or
more issues is a burst and each issue belongs to at most one burst.

Different than ``list_issues.py`` and than issue #5702 step 5: it runs a manual
page loop over ``gh api`` with fail-closed semantics instead of a capped
``gh issue list`` call, since a cap is not pagination. It defines its own
``--output-format`` (markdown or json) instead of ``add_output_format_arg``,
because ``github_core.output`` "auto" switches to JSON when stdout is
redirected and the issue requires a deterministic default. A page whose records
are all repeats aborts the run with exit 3, so a shifting page boundary can
cost a retry but never a silent miscount.

EXIT CODES (ADR-035):
    0 - Report produced from a complete read
    2 - Config error (invalid --days, --until, or repository)
    3 - External error (GitHub API failure, malformed page, rate limit)
    4 - Auth error (gh missing or not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "lib"))
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    REST_PAGE_PACE_SECONDS,
    GhAuthStatus,
    check_gh_auth,
    classify_gh_failure_text,
    describe_gh_auth_failure,
    is_auth_failure_text,
    resolve_repo_params,
)
from github_core.output import write_skill_error, write_skill_output  # noqa: E402

SCRIPT_NAME = "backlog_provenance.py"
PAGE_SIZE = 100
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


def parse_record(record: object) -> Issue:
    """Build an Issue from one REST issue record, or raise ReportError (exit 3)."""
    if not isinstance(record, dict):
        raise ReportError(f"Malformed issue record: {type(record).__name__}", 3, "ApiError")
    number = record.get("number")
    if isinstance(number, bool) or not isinstance(number, int):
        raise ReportError(f"Issue record has no integer number: {number!r}", 3, "ApiError")
    return Issue(
        number=number,
        title=str(record.get("title") or ""),
        login=_login(record, number),
        created_at=parse_timestamp(record.get("created_at")),
        labels=_label_names(record, number),
    )


def _label_names(record: dict[str, Any], number: int) -> frozenset[str]:
    labels = record.get("labels")
    if not isinstance(labels, list):
        raise ReportError(f"Issue {number} has malformed labels: {labels!r}", 3, "ApiError")
    return frozenset(
        str(label.get("name", "")).lower() for label in labels if isinstance(label, dict)
    )


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


def build_endpoint(owner: str, repo: str, since: datetime) -> str:
    stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"repos/{owner}/{repo}/issues?state=all&since={stamp}&per_page={PAGE_SIZE}"


def fetch_page(endpoint: str, page: int) -> list[Any]:
    """Fetch one REST page. Any failure raises ReportError; nothing is retried."""
    separator = "&" if "?" in endpoint else "?"
    try:
        result = subprocess.run(
            ["gh", "api", f"{endpoint}{separator}page={page}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReportError(f"Timed out reading page {page}", 3, "Timeout") from exc
    except FileNotFoundError as exc:
        raise ReportError("gh CLI not found on PATH.", 4, "AuthError") from exc
    if result.returncode != 0:
        raise _page_failure(page, (result.stderr or result.stdout).strip())
    return _decode_page(page, result.stdout)


def _page_failure(page: int, detail: str) -> ReportError:
    if is_auth_failure_text(detail):
        return ReportError(f"Authentication failure on page {page}: {detail}", 4, "AuthError")
    status = classify_gh_failure_text(detail)
    if status in (GhAuthStatus.RATE_LIMITED, GhAuthStatus.SECONDARY_RATE_LIMITED):
        return ReportError(f"Rate limit on page {page}: {detail}", 3, "ApiError")
    return ReportError(f"Failed to read page {page}: {detail}", 3, "ApiError")


def _decode_page(page: int, stdout: str) -> list[Any]:
    try:
        items = json.loads(stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReportError(f"Malformed JSON on page {page}: {exc}", 3, "ApiError") from exc
    if not isinstance(items, list):
        raise ReportError(f"Page {page} is {type(items).__name__}, expected a list", 3, "ApiError")
    return items


def collect_backlog(
    endpoint: str,
    start: datetime,
    end: datetime,
    fetcher: Callable[[str, int], list[Any]] | None = None,
    pacer: Callable[[float], None] | None = None,
) -> Backlog:
    """Read every page until an empty one and keep issues created in [start, end)."""
    fetch = fetcher or fetch_page
    pause = pacer or time.sleep
    backlog = Backlog()
    seen: set[int] = set()
    page = 1
    while True:
        items = fetch(endpoint, page)
        if not items:
            return backlog
        backlog.stats.pages += 1
        backlog.stats.records_fetched += len(items)
        if not _absorb_page(items, backlog, seen, start, end, page):
            raise ReportError(f"Pagination did not advance at page {page}", 3, "ApiError")
        pause(REST_PAGE_PACE_SECONDS)
        page += 1


def _absorb_page(
    items: list[Any],
    backlog: Backlog,
    seen: set[int],
    start: datetime,
    end: datetime,
    page: int,
) -> bool:
    """Add one page to the backlog. Return False when no record was new."""
    advanced = False
    for record in items:
        if isinstance(record, dict) and "pull_request" in record:
            backlog.stats.pull_requests_excluded += 1
            advanced = True
            continue
        issue = parse_record(record)
        if issue.number in seen:
            backlog.stats.duplicates_dropped += 1
            continue
        seen.add(issue.number)
        advanced = True
        if start <= issue.created_at < end:
            backlog.issues.append(issue)
        else:
            backlog.stats.out_of_window_excluded += 1
    return advanced


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report the provenance split of new GitHub issues (read-only).",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--days", type=int, default=7, help="Window length in days (default 7)")
    parser.add_argument(
        "--until",
        default="",
        help="Window end as a UTC ISO-8601 timestamp (default: now). Exclusive.",
    )
    parser.add_argument(
        "--output-format",
        choices=["markdown", "json"],
        default="markdown",
        help="markdown (default, also when redirected) or json",
    )
    return parser


def resolve_window(days: int, until: str, now: datetime) -> tuple[datetime, datetime]:
    """Return [start, end) in UTC, or raise ReportError (exit 2)."""
    if days < 1:
        raise ReportError(f"--days must be at least 1, got {days}", 2, "InvalidParams")
    try:
        return _window_bounds(days, until, now)
    except OverflowError as exc:
        raise ReportError(f"--days or --until is out of range: {exc}", 2, "InvalidParams") from exc


def _window_bounds(days: int, until: str, now: datetime) -> tuple[datetime, datetime]:
    if not until:
        return now - timedelta(days=days), now
    try:
        end = datetime.fromisoformat(until.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReportError(f"--until is not ISO-8601: {until!r}", 2, "InvalidParams") from exc
    if end.tzinfo is None:
        raise ReportError(
            "--until needs a timezone, for example 2026-09-29T00:00:00Z", 2, "InvalidParams"
        )
    end = end.astimezone(timezone.utc)
    return end - timedelta(days=days), end


def _require_auth() -> None:
    result = check_gh_auth()
    if result.status is not GhAuthStatus.AUTHENTICATED:
        message, code, error_type = describe_gh_auth_failure(result)
        raise ReportError(message, code, error_type)


def _emit(report: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        write_skill_output(report, output_format="json", script_name=SCRIPT_NAME)
        return
    print(render_markdown(report))


def run(args: argparse.Namespace, now: datetime) -> dict[str, Any]:
    start, end = resolve_window(args.days, args.until, now)
    _require_auth()
    repo = resolve_repo_params(args.owner, args.repo)
    endpoint = build_endpoint(repo.owner, repo.repo, start)
    backlog = collect_backlog(endpoint, start, end)
    return build_report(backlog, repo.owner, repo.repo, endpoint, start, end, now)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        report = run(args, now)
    except ReportError as exc:
        write_skill_error(
            str(exc),
            exc.exit_code,
            error_type=exc.error_type,
            output_format="json" if args.output_format == "json" else "human",
            script_name=SCRIPT_NAME,
        )
        return exc.exit_code
    _emit(report, args.output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
