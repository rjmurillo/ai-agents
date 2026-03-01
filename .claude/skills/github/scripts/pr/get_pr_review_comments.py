#!/usr/bin/env python3
"""Get all review comments on a PR with domain classification.

Fetches review comments (and optionally issue comments) with domain
classification, stale detection, and filtering by author or bot status.

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
    gh_api_paginated,
    resolve_repo_params,
    write_error_and_exit,
)

DOMAIN_PATTERNS = {
    "security": [
        "cwe", "vulnerability", "injection", "xss",
        "csrf", "secret", "credential", "traversal",
    ],
    "bug": [
        "error", "exception", "crash", "null",
        "undefined", "race condition", "deadlock",
    ],
    "style": [
        "naming", "convention", "lint", "indent",
        "format", "whitespace", "readability",
    ],
    "summary": ["lgtm", "approve", "good", "merge", "looks good"],
}


def classify_domain(body: str) -> str:
    """Classify a comment body into a domain based on keywords."""
    if not body:
        return "general"
    lower = body.lower()
    for domain, keywords in DOMAIN_PATTERNS.items():
        if any(kw in lower for kw in keywords):
            return domain
    return "general"


def is_stale(comment: dict, latest_commit_date: str | None) -> bool:
    """Check if a comment predates the latest commit."""
    if not latest_commit_date:
        return False
    created_at: str = comment.get("created_at", "")
    return created_at < latest_commit_date


def format_comment(comment: dict, stale: bool) -> dict[str, object]:
    """Format a raw API comment into the output structure."""
    return {
        "Id": comment["id"],
        "Author": comment.get("user", {}).get("login", "unknown"),
        "AuthorType": comment.get("user", {}).get("type", "User"),
        "Body": comment.get("body", "")[:200],
        "Domain": classify_domain(comment.get("body", "")),
        "CreatedAt": comment.get("created_at"),
        "Path": comment.get("path"),
        "Line": comment.get("line") or comment.get("original_line"),
        "IsStale": stale,
    }


def get_latest_commit_date(owner: str, repo: str, pr: int) -> str | None:
    """Get the date of the latest commit on the PR."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr), "--repo", f"{owner}/{repo}",
             "--json", "commits", "--jq", ".commits[-1].committedDate"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Get PR review comments with domain classification",
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument("--author", help="Filter by comment author login")
    parser.add_argument(
        "--include-issue-comments", action="store_true",
        help="Also fetch issue comments",
    )
    parser.add_argument(
        "--detect-stale", action="store_true",
        help="Mark comments older than latest commit",
    )
    parser.add_argument(
        "--only-unaddressed", action="store_true",
        help="Only comments with no eyes reaction",
    )
    parser.add_argument(
        "--bot-only", action="store_true",
        help="Only bot comments (with --only-unaddressed)",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    review_endpoint = (
        f"repos/{owner}/{repo}/pulls/{args.pull_request}/comments"
    )
    try:
        review_comments = gh_api_paginated(review_endpoint)
    except Exception as e:
        write_error_and_exit(f"Failed to fetch review comments: {e}", 3)

    issue_comments = []
    if args.include_issue_comments:
        issue_endpoint = (
            f"repos/{owner}/{repo}/issues/{args.pull_request}/comments"
        )
        try:
            issue_comments = gh_api_paginated(issue_endpoint)
        except Exception as e:
            write_error_and_exit(f"Failed to fetch issue comments: {e}", 3)

    all_raw = review_comments + issue_comments

    latest_commit_date = None
    if args.detect_stale:
        latest_commit_date = get_latest_commit_date(owner, repo, args.pull_request)

    # Apply filters
    filtered = all_raw
    if args.author:
        filtered = [c for c in filtered if c.get("user", {}).get("login") == args.author]
    if args.only_unaddressed:
        filtered = [c for c in filtered if c.get("reactions", {}).get("eyes", 0) == 0]
        if args.bot_only:
            filtered = [c for c in filtered if c.get("user", {}).get("type") == "Bot"]

    comments = [format_comment(c, is_stale(c, latest_commit_date)) for c in filtered]

    # Build domain counts
    domain_counts: dict[str, int] = {}
    for c in comments:
        domain = str(c["Domain"])
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    # Build author summary
    author_map: dict[str, int] = {}
    for c in comments:
        author = str(c["Author"])
        author_map[author] = author_map.get(author, 0) + 1
    author_summary = [{"Author": a, "Count": n} for a, n in author_map.items()]

    output = {
        "Success": True,
        "PullRequest": args.pull_request,
        "Owner": owner,
        "Repo": repo,
        "TotalComments": len(comments),
        "Comments": comments,
        "DomainCounts": domain_counts,
        "AuthorSummary": author_summary,
    }

    print(json.dumps(output, indent=2))
    print(f"PR #{args.pull_request}: {len(comments)} review comments", file=sys.stderr)


if __name__ == "__main__":
    main()
