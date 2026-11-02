#!/usr/bin/env python3
"""Backlog provenance report for new issues (issue #5702, epic #5698).

Read-only diagnostic. It reports how many issues were created in an explicit
UTC interval, split by recorded ``source:*`` label, plus two labeled
heuristics (machinery titles and creation bursts). It is not a productivity
score and it never files, labels, or closes an issue. The bucket, heuristic,
and rendering rules live in ``backlog_provenance_report.py``.

Completeness: the REST issue list is read page by page until an empty page.
Any failed or malformed page aborts the run with exit 3. Partial counts are
never published as complete. Pull-request records are excluded and records are
deduplicated by immutable issue number.

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
import subprocess
import sys
import time
from collections.abc import Callable
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

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from backlog_provenance_report import (  # noqa: E402
    Backlog,
    ReportError,
    build_report,
    parse_record,
    record_number,
    render_markdown,
)

SCRIPT_NAME = "backlog_provenance.py"
PAGE_SIZE = 100


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
        if not _absorb_page(items, backlog, seen, start, end):
            raise ReportError(f"Pagination did not advance at page {page}", 3, "ApiError")
        pause(REST_PAGE_PACE_SECONDS)
        page += 1


def _absorb_page(
    items: list[Any],
    backlog: Backlog,
    seen: set[int],
    start: datetime,
    end: datetime,
) -> bool:
    """Add one page to the backlog. Return False when no record was new."""
    results = [_absorb_record(record, backlog, seen, start, end) for record in items]
    return any(results)


def _absorb_record(
    record: Any, backlog: Backlog, seen: set[int], start: datetime, end: datetime
) -> bool:
    """Add one record. Return False when its number was already seen."""
    is_pull_request = isinstance(record, dict) and "pull_request" in record
    issue = None if is_pull_request else parse_record(record)
    number = record_number(record) if issue is None else issue.number
    if number in seen:
        backlog.stats.duplicates_dropped += 1
        return False
    seen.add(number)
    if issue is None:
        backlog.stats.pull_requests_excluded += 1
    elif start <= issue.created_at < end:
        backlog.issues.append(issue)
    else:
        backlog.stats.out_of_window_excluded += 1
    return True


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
