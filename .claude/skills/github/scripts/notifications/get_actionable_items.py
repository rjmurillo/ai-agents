#!/usr/bin/env python3
"""List actionable backlog items from GitHub without gh-notify.

Queries PRs and issues that need attention using gh CLI. Falls back
gracefully when the notifications API returns 403 (common with
GitHub App tokens and fine-grained PATs).

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
    resolve_repo_params,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List actionable backlog items (PRs and issues needing attention).",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--limit", type=int, default=20,
        help="Max items per category (1-100, default: 20)",
    )
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
        capture_output=True, text=True, timeout=15, check=False,
    )
    if result.returncode != 0:
        error_and_exit(
            f"Failed to determine current user: {result.stderr or result.stdout}", 4,
        )
    return result.stdout.strip()


def _try_notifications(repo_flag: str, limit: int) -> list[dict] | None:
    """Attempt to fetch notifications via the REST API.

    Returns None if the API returns 403 or is otherwise inaccessible.
    """
    result = subprocess.run(
        [
            "gh", "api", "notifications",
            "--jq", (
                f'[.[] | select(.repository.full_name == "{repo_flag}") '
                f'| {{reason: .reason, title: .subject.title, '
                f'type: .subject.type, url: .subject.url, '
                f'updated_at: .updated_at}}] | .[:' + str(limit) + ']'
            ),
        ],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr or ""
        if "403" in stderr or "Resource not accessible" in stderr:
            return None
        return None

    try:
        return json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        return None


def _get_review_requests(repo_flag: str, user: str, limit: int) -> list[dict]:
    """Fetch PRs where the current user is requested as reviewer."""
    result = subprocess.run(
        [
            "gh", "pr", "list",
            "--repo", repo_flag,
            "--search", f"review-requested:{user}",
            "--limit", str(limit),
            "--json", "number,title,author,updatedAt,url",
        ],
        capture_output=True, text=True, timeout=30, check=False,
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
            "gh", "pr", "list",
            "--repo", repo_flag,
            "--author", user,
            "--limit", str(limit),
            "--json", "number,title,reviewDecision,updatedAt,url",
        ],
        capture_output=True, text=True, timeout=30, check=False,
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
            "gh", "issue", "list",
            "--repo", repo_flag,
            "--assignee", user,
            "--limit", str(limit),
            "--json", "number,title,labels,updatedAt,url",
        ],
        capture_output=True, text=True, timeout=30, check=False,
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

    if not 1 <= args.limit <= 100:
        error_and_exit("Limit must be between 1 and 100.", 1)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]
    repo_flag = f"{owner}/{repo}"
    _validate_repo_flag(repo_flag)

    user = _get_current_user()

    # Try notifications API first
    notifications = _try_notifications(repo_flag, args.limit)
    notifications_available = notifications is not None

    # Always gather fallback data (useful even when notifications work)
    review_requests = _get_review_requests(repo_flag, user, args.limit)
    authored_prs = _get_authored_prs(repo_flag, user, args.limit)
    assigned_issues = _get_assigned_issues(repo_flag, user, args.limit)

    output = {
        "success": True,
        "user": user,
        "repo": repo_flag,
        "notifications_api_available": notifications_available,
        "notifications": notifications if notifications_available else [],
        "review_requests": review_requests,
        "authored_prs": authored_prs,
        "assigned_issues": assigned_issues,
        "summary": {
            "notifications": len(notifications) if notifications_available else 0,
            "review_requests": len(review_requests),
            "authored_prs": len(authored_prs),
            "assigned_issues": len(assigned_issues),
        },
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
