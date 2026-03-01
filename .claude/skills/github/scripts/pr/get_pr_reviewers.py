#!/usr/bin/env python3
"""Get unique reviewers for a GitHub Pull Request.

Collects reviewers from PR reviews, review comments, and issue comments
to build a deduplicated list with participation counts.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = PR not found
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


def is_bot_user(login: str, user_type: str) -> bool:
    """Determine if a user is a bot based on type or login suffix."""
    if user_type == "Bot":
        return True
    return login.endswith("[bot]")


def get_pr_data(owner: str, repo: str, pr: int) -> dict:
    """Fetch PR metadata including author, review requests, and reviews."""
    result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", f"{owner}/{repo}",
         "--json", "author,reviewRequests,reviews"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if "not found" in result.stderr.lower() or "Could not resolve" in result.stderr:
            write_error_and_exit(f"PR #{pr} not found in {owner}/{repo}", 2)
        write_error_and_exit(f"Failed to fetch PR data: {result.stderr}", 3)
    pr_data: dict = json.loads(result.stdout)
    return pr_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Get unique PR reviewers")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument("--exclude-bots", action="store_true", help="Exclude bot accounts")
    parser.add_argument("--exclude-author", action="store_true", help="Exclude PR author")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    pr_data = get_pr_data(owner, repo, args.pull_request)
    pr_author = pr_data.get("author", {}).get("login", "")

    # Reviewer map: login -> {type, reviewComments, issueComments}
    reviewers: dict[str, dict] = {}

    def add_reviewer(login: str, user_type: str) -> None:
        if login not in reviewers:
            reviewers[login] = {
                "login": login,
                "type": user_type,
                "isBot": is_bot_user(login, user_type),
                "reviewComments": 0,
                "issueComments": 0,
            }

    # From formal reviews
    for review in pr_data.get("reviews", []):
        login = review.get("author", {}).get("login")
        if login:
            add_reviewer(login, review.get("author", {}).get("type", "User"))

    # From review requests
    for req in pr_data.get("reviewRequests", []):
        login = req.get("login")
        if login:
            add_reviewer(login, req.get("type", "User"))

    # From review comments (REST API)
    try:
        review_comments = gh_api_paginated(
            f"repos/{owner}/{repo}/pulls/{args.pull_request}/comments"
        )
        for c in review_comments:
            login = c.get("user", {}).get("login")
            user_type = c.get("user", {}).get("type", "User")
            if login:
                add_reviewer(login, user_type)
                reviewers[login]["reviewComments"] += 1
    except Exception:
        pass

    # From issue comments (REST API)
    try:
        issue_comments = gh_api_paginated(
            f"repos/{owner}/{repo}/issues/{args.pull_request}/comments"
        )
        for c in issue_comments:
            login = c.get("user", {}).get("login")
            user_type = c.get("user", {}).get("type", "User")
            if login:
                add_reviewer(login, user_type)
                reviewers[login]["issueComments"] += 1
    except Exception:
        pass

    # Apply filters
    result_list = list(reviewers.values())
    if args.exclude_bots:
        result_list = [r for r in result_list if not r["isBot"]]
    if args.exclude_author and pr_author:
        result_list = [r for r in result_list if r["login"] != pr_author]

    output = {
        "Success": True,
        "PullRequest": args.pull_request,
        "Owner": owner,
        "Repo": repo,
        "TotalReviewers": len(result_list),
        "PRAuthor": pr_author,
        "Reviewers": result_list,
    }

    print(json.dumps(output, indent=2))
    print(f"PR #{args.pull_request}: {len(result_list)} unique reviewers", file=sys.stderr)


if __name__ == "__main__":
    main()
