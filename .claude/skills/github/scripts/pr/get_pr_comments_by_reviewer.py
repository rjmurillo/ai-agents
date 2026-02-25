#!/usr/bin/env python3
"""Get PR comments grouped by reviewer login.

Retrieves review comments and optionally issue comments for one or more PRs,
then groups them by reviewer. Supports filtering by reviewer, date range,
and comment type.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters
    2 - Not found
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    gh_api_paginated,
    resolve_repo_params,
)

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _parse_iso_date(date_str: str) -> datetime | None:
    """Parse an ISO 8601 date string to a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _fetch_pr_author(owner: str, repo: str, pr_number: int) -> str:
    """Fetch the PR author login."""
    result = subprocess.run(
        [
            "gh", "pr", "view", str(pr_number),
            "--repo", f"{owner}/{repo}",
            "--json", "author",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        err_msg = result.stderr or result.stdout
        if "not found" in err_msg.lower():
            error_and_exit(f"PR #{pr_number} not found", 2)
        error_and_exit(f"Failed to get PR #{pr_number}: {err_msg}", 3)
    data = json.loads(result.stdout)
    return (data.get("author") or {}).get("login", "")


def get_pr_comments_by_reviewer(
    owner: str,
    repo: str,
    pr_numbers: list[int],
    *,
    include_reviewers: list[str] | None = None,
    exclude_reviewers: list[str] | None = None,
    since: str = "",
    until: str = "",
    comment_type: str = "all",
    exclude_self_comments: bool = True,
) -> dict[str, Any]:
    """Group PR comments by reviewer login.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pr_numbers: List of PR numbers to fetch comments from.
        include_reviewers: Only include these reviewer logins.
        exclude_reviewers: Exclude these reviewer logins.
        since: ISO 8601 date; only comments after this date.
        until: ISO 8601 date; only comments before this date.
        comment_type: "review", "issue", or "all".
        exclude_self_comments: Skip comments by the PR author on their own PR.

    Returns:
        Dict with grouped reviewer data and summary.
    """
    since_dt = _parse_iso_date(since)
    until_dt = _parse_iso_date(until)
    include_set = set(include_reviewers) if include_reviewers else None
    exclude_set = set(exclude_reviewers) if exclude_reviewers else set()

    reviewer_map: dict[str, dict[str, Any]] = {}
    total_comments = 0
    prs_processed = 0

    for pr_number in pr_numbers:
        pr_author = _fetch_pr_author(owner, repo, pr_number)
        comments: list[dict] = []

        if comment_type in ("review", "all"):
            review_comments = gh_api_paginated(
                f"repos/{owner}/{repo}/pulls/{pr_number}/comments"
            )
            for c in review_comments:
                comments.append({
                    "login": (c.get("user") or {}).get("login", ""),
                    "user_type": (c.get("user") or {}).get("type", "User"),
                    "body": c.get("body", ""),
                    "created_at": c.get("created_at", ""),
                    "updated_at": c.get("updated_at", ""),
                    "path": c.get("path"),
                    "html_url": c.get("html_url"),
                    "comment_type": "review",
                    "pr_number": pr_number,
                })

        if comment_type in ("issue", "all"):
            issue_comments = gh_api_paginated(
                f"repos/{owner}/{repo}/issues/{pr_number}/comments"
            )
            for c in issue_comments:
                comments.append({
                    "login": (c.get("user") or {}).get("login", ""),
                    "user_type": (c.get("user") or {}).get("type", "User"),
                    "body": c.get("body", ""),
                    "created_at": c.get("created_at", ""),
                    "updated_at": c.get("updated_at", ""),
                    "path": None,
                    "html_url": c.get("html_url"),
                    "comment_type": "issue",
                    "pr_number": pr_number,
                })

        for comment in comments:
            login = comment["login"]
            if not login:
                continue
            if exclude_self_comments and login == pr_author:
                continue
            if include_set and login not in include_set:
                continue
            if login in exclude_set:
                continue

            created_dt = _parse_iso_date(comment["created_at"])
            if since_dt and created_dt and created_dt < since_dt:
                continue
            if until_dt and created_dt and created_dt > until_dt:
                continue

            if login not in reviewer_map:
                reviewer_map[login] = {
                    "login": login,
                    "user_type": comment["user_type"],
                    "total_comments": 0,
                    "review_comments": 0,
                    "issue_comments": 0,
                    "prs": [],
                    "comments": [],
                }

            entry = reviewer_map[login]
            entry["total_comments"] += 1
            if comment["comment_type"] == "review":
                entry["review_comments"] += 1
            else:
                entry["issue_comments"] += 1
            if pr_number not in entry["prs"]:
                entry["prs"].append(pr_number)
            entry["comments"].append({
                "pr_number": comment["pr_number"],
                "body": comment["body"],
                "created_at": comment["created_at"],
                "path": comment["path"],
                "html_url": comment["html_url"],
                "comment_type": comment["comment_type"],
            })
            total_comments += 1

        prs_processed += 1

    reviewers = sorted(
        reviewer_map.values(),
        key=lambda r: r["total_comments"],
        reverse=True,
    )

    output = {
        "success": True,
        "owner": owner,
        "repo": repo,
        "prs_processed": prs_processed,
        "total_reviewers": len(reviewers),
        "total_comments": total_comments,
        "reviewers": reviewers,
    }

    reviewer_summary = ", ".join(
        f"{r['login']}({r['total_comments']})" for r in reviewers[:5]
    )
    print(
        f"Grouped {total_comments} comments from {prs_processed} PR(s) "
        f"across {len(reviewers)} reviewer(s): {reviewer_summary}",
        file=sys.stderr,
    )

    return output


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get PR comments grouped by reviewer login.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, nargs="+", required=True,
        help="One or more PR numbers",
    )
    parser.add_argument(
        "--include-reviewer", nargs="*", default=None,
        help="Only include these reviewer logins",
    )
    parser.add_argument(
        "--exclude-reviewer", nargs="*", default=None,
        help="Exclude these reviewer logins",
    )
    parser.add_argument(
        "--since", default="",
        help="Only comments after this ISO 8601 date",
    )
    parser.add_argument(
        "--until", default="",
        help="Only comments before this ISO 8601 date",
    )
    parser.add_argument(
        "--comment-type", choices=["review", "issue", "all"], default="all",
        help="Type of comments to include (default: all)",
    )
    parser.add_argument(
        "--include-self-comments", action="store_true",
        help="Include comments by the PR author on their own PR",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    result = get_pr_comments_by_reviewer(
        owner,
        repo,
        args.pull_request,
        include_reviewers=args.include_reviewer,
        exclude_reviewers=args.exclude_reviewer,
        since=args.since,
        until=args.until,
        comment_type=args.comment_type,
        exclude_self_comments=not args.include_self_comments,
    )

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
