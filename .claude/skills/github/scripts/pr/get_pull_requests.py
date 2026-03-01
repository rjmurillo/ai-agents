#!/usr/bin/env python3
"""List GitHub Pull Requests with optional filters.

Supports filtering by state, label, author, base branch, and head branch.
Returns structured JSON with PR metadata.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import subprocess
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
    write_error_and_exit,
)

MAX_LIMIT = 1000
JSON_FIELDS = "number,title,headRefName,baseRefName,state,url,isDraft,author,createdAt"


def main() -> None:
    parser = argparse.ArgumentParser(description="List GitHub Pull Requests")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument(
        "--state",
        choices=["open", "closed", "merged", "all"],
        default="open",
        help="PR state filter (default: open)",
    )
    parser.add_argument("--label", help="Filter by label")
    parser.add_argument("--author", help="Filter by author")
    parser.add_argument("--base", help="Filter by base branch")
    parser.add_argument("--head", help="Filter by head branch")
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Maximum number of PRs to return (default: 30, max: 1000)",
    )
    args = parser.parse_args()

    if args.limit < 1 or args.limit > MAX_LIMIT:
        write_error_and_exit(f"Limit must be between 1 and {MAX_LIMIT}", 1)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    cmd = [
        "gh", "pr", "list",
        "--repo", f"{owner}/{repo}",
        "--json", JSON_FIELDS,
        "--limit", str(args.limit),
    ]

    if args.state != "all":
        cmd.extend(["--state", args.state])

    if args.label:
        cmd.extend(["--label", args.label])

    if args.author:
        cmd.extend(["--author", args.author])

    if args.base:
        cmd.extend(["--base", args.base])

    if args.head:
        cmd.extend(["--head", args.head])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        write_error_and_exit(f"Failed to list PRs: {result.stderr}", 3)

    prs = json.loads(result.stdout)

    pull_requests = []
    for pr in prs:
        author_login = ""
        if isinstance(pr.get("author"), dict):
            author_login = pr["author"].get("login", "")

        pull_requests.append({
            "Number": pr.get("number"),
            "Title": pr.get("title"),
            "Head": pr.get("headRefName"),
            "Base": pr.get("baseRefName"),
            "State": pr.get("state"),
            "Url": pr.get("url"),
            "IsDraft": pr.get("isDraft", False),
            "Author": author_login,
            "CreatedAt": pr.get("createdAt"),
        })

    output = {
        "Success": True,
        "Count": len(pull_requests),
        "PullRequests": pull_requests,
    }
    print(json.dumps(output, indent=2))
    count = len(pull_requests)
    print(
        f"Found {count} PR(s) in {owner}/{repo}"
        f" (state: {args.state})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
