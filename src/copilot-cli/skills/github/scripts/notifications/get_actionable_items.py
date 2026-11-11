#!/usr/bin/env python3
"""List actionable backlog items from GitHub without gh-notify.

Queries PRs and issues that need attention using gh CLI. Falls back
gracefully when the notifications API returns 403 or a missing-scope response
(common with GitHub App tokens and fine-grained PATs). Any other notifications
failure, such as a rate limit or a 5xx, exits 3 instead of reading as
"unavailable". Notifications are paged to the end before the repository filter
and ``--limit`` apply; ``notifications_matched`` and ``notifications_truncated``
report what the limit cut.

Sources checked (in order):
1. GitHub notifications API (if accessible)
2. PRs requesting your review
3. PRs authored by you that need attention
4. Issues assigned to you

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_HELP_EPILOG = """\
examples:
  %(prog)s
  %(prog)s --limit 25 --output-format json

exit codes:
  0  success
  1  invalid parameters / logic error
  2  invalid owner or repo, or plugin lib missing
  3  external error (API failure)
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List actionable backlog items (PRs and issues needing attention).",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max items per category (1-100, default: 20)",
    )
    add_output_format_arg(parser)
    return parser


_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def _validate_repo_flag(repo_flag: str) -> None:
    """Reject repo_flag values that could inject into shell or jq."""
    if not _REPO_PATTERN.match(repo_flag):
        error_and_exit(f"Invalid repository format: {repo_flag}", 1)


def _get_current_user() -> str:
    """Return the authenticated GitHub username."""
    result = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        error_and_exit(
            f"Failed to determine current user: {result.stderr or result.stdout}",
            4,
        )
    return result.stdout.strip()


class NotificationsError(Exception):
    """The notifications read failed for a reason other than "API unavailable"."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


_NOTIFICATIONS_TIMEOUT_SECONDS = 180
_RATE_LIMIT_MARKERS = ("rate limit", "http 429", "abuse detection")
_UNAVAILABLE_MARKERS = ("http 403", "resource not accessible", "missing scope", "required scope")


def _classify_notifications_failure(stderr: str) -> str:
    """Return "unavailable" for a 403 or missing scope, else "rate_limit", "auth", "error".

    A rate limit also answers 403, so the rate-limit markers are checked first.
    Only a 403 or a missing-scope response means the API is unavailable to this
    token. Anything else is a failure the caller must report.
    """
    text = stderr.lower()
    if any(marker in text for marker in _RATE_LIMIT_MARKERS):
        return "rate_limit"
    # gh prints: This API operation needs the "notifications" scope.
    needs_scope = "needs the" in text and "scope" in text
    if needs_scope or any(marker in text for marker in _UNAVAILABLE_MARKERS):
        return "unavailable"
    if "http 401" in text:
        return "auth"
    return "error"


def _try_notifications(repo_flag: str) -> list[dict] | None:
    """Read every notification page for the repository.

    Pages to the end with ``gh api --paginate``, then filters to the repository.
    The caller applies any limit afterward, so the matched count stays exact.

    Returns None only when the API answers 403 or a missing scope (common with
    GitHub App tokens and fine-grained PATs).

    Raises:
        NotificationsError: Rate limit, 5xx, auth failure, timeout, or output
            that is not valid JSON. The result is never partial.
    """
    jq_filter = (
        f'.[] | select(.repository.full_name == "{repo_flag}") '
        "| {reason: .reason, title: .subject.title, "
        "type: .subject.type, url: .subject.url, updated_at: .updated_at}"
    )
    try:
        result = subprocess.run(
            [
                "gh",
                "api",
                # per_page rides in the URL: a -f field would turn this into a POST.
                "notifications?per_page=100",
                "--paginate",
                "--jq",
                jq_filter,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_NOTIFICATIONS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise NotificationsError(
            f"Notifications read timed out after {_NOTIFICATIONS_TIMEOUT_SECONDS}s", 3
        ) from exc
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        kind = _classify_notifications_failure(stderr)
        if kind == "unavailable":
            return None
        exit_code = 4 if kind == "auth" else 3
        label = "rate limited" if kind == "rate_limit" else "failed"
        raise NotificationsError(f"Notifications read {label}: {stderr}", exit_code)

    items: list[dict] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise NotificationsError(f"Notifications read returned invalid JSON: {exc}", 3) from exc
    return items


def _get_review_requests(repo_flag: str, user: str, limit: int) -> list[dict]:
    """Fetch PRs where the current user is requested as reviewer."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo_flag,
            "--search",
            f"review-requested:{user}",
            "--limit",
            str(limit),
            "--json",
            "number,title,author,updatedAt,url",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return []

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    return [
        {
            "number": p.get("number"),
            "title": p.get("title"),
            "author": (p.get("author") or {}).get("login", "unknown"),
            "updated_at": p.get("updatedAt"),
            "url": p.get("url"),
            "reason": "review_requested",
        }
        for p in prs
    ]


def _get_authored_prs(repo_flag: str, user: str, limit: int) -> list[dict]:
    """Fetch open PRs authored by the current user."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo_flag,
            "--author",
            user,
            "--limit",
            str(limit),
            "--json",
            "number,title,reviewDecision,updatedAt,url",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return []

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    return [
        {
            "number": p.get("number"),
            "title": p.get("title"),
            "review_decision": p.get("reviewDecision"),
            "updated_at": p.get("updatedAt"),
            "url": p.get("url"),
            "reason": "authored",
        }
        for p in prs
    ]


def _get_assigned_issues(repo_flag: str, user: str, limit: int) -> list[dict]:
    """Fetch open issues assigned to the current user."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo_flag,
            "--assignee",
            user,
            "--limit",
            str(limit),
            "--json",
            "number,title,labels,updatedAt,url",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return []

    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    return [
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "labels": [lbl.get("name") for lbl in (i.get("labels") or [])],
            "updated_at": i.get("updatedAt"),
            "url": i.get("url"),
            "reason": "assigned",
        }
        for i in issues
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    if not 1 <= args.limit <= 100:
        write_skill_error(
            "Limit must be between 1 and 100.",
            1,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="get_actionable_items.py",
            extra={"limit": args.limit},
        )
        return 1

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    repo_flag = f"{owner}/{repo}"
    _validate_repo_flag(repo_flag)

    user = _get_current_user()

    # Try notifications API first. Page to the end, then apply the limit.
    try:
        all_notifications = _try_notifications(repo_flag)
    except NotificationsError as exc:
        write_skill_error(
            str(exc),
            exc.exit_code,
            error_type="ApiError" if exc.exit_code == 3 else "AuthError",
            output_format=fmt,
            script_name="get_actionable_items.py",
            extra={"repo": repo_flag, "notifications_api_available": None},
        )
        return exc.exit_code
    notifications_available = all_notifications is not None
    matched_notifications = len(all_notifications) if all_notifications is not None else 0
    notifications = (all_notifications or [])[: args.limit]
    notifications_truncated = matched_notifications > len(notifications)

    # Always gather fallback data (useful even when notifications work)
    review_requests = _get_review_requests(repo_flag, user, args.limit)
    authored_prs = _get_authored_prs(repo_flag, user, args.limit)
    assigned_issues = _get_assigned_issues(repo_flag, user, args.limit)

    data = {
        "user": user,
        "repo": repo_flag,
        "notifications_api_available": notifications_available,
        "notifications": notifications,
        "notifications_matched": matched_notifications,
        "notifications_truncated": notifications_truncated,
        "review_requests": review_requests,
        "authored_prs": authored_prs,
        "assigned_issues": assigned_issues,
        "summary": {
            "notifications": len(notifications),
            "review_requests": len(review_requests),
            "authored_prs": len(authored_prs),
            "assigned_issues": len(assigned_issues),
        },
    }

    total = (
        data["summary"]["notifications"]
        + data["summary"]["review_requests"]
        + data["summary"]["authored_prs"]
        + data["summary"]["assigned_issues"]
    )
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"Found {total} actionable item(s) for {user} in {repo_flag}",
        script_name="get_actionable_items.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
