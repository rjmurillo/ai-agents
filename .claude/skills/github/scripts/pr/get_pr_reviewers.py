#!/usr/bin/env python3
"""Get unique reviewers for a GitHub Pull Request.

Enumerates all unique reviewers from review comments, issue comments,
requested reviewers, and submitted reviews. Critical for avoiding
"single-bot blindness" per Skill-PR-001.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
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
    gh_api_paginated,
    resolve_repo_params,
)

_BOT_SUFFIX = re.compile(r"\[bot\]$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get unique reviewers for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--exclude-bots", action="store_true", help="Exclude bot accounts",
    )
    parser.add_argument(
        "--exclude-author", action="store_true", help="Exclude the PR author",
    )
    return parser


def _is_bot(login: str, user_type: str) -> bool:
    return user_type == "Bot" or bool(_BOT_SUFFIX.search(login))


def _ensure_reviewer(reviewer_map: dict, login: str, user_type: str) -> None:
    if login not in reviewer_map:
        reviewer_map[login] = {
            "login": login,
            "type": user_type,
            "is_bot": _is_bot(login, user_type),
            "review_comments": 0,
            "issue_comments": 0,
        }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request

    pr_result = subprocess.run(
        [
            "gh", "pr", "view", str(pr),
            "--repo", f"{owner}/{repo}",
            "--json", "author,reviewRequests,reviews",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if pr_result.returncode != 0:
        err_msg = pr_result.stderr or pr_result.stdout
        if "not found" in err_msg:
            error_and_exit(f"PR #{pr} not found", 2)
        error_and_exit(f"Failed to get PR: {err_msg}", 3)

    pr_data = json.loads(pr_result.stdout)
    pr_author = pr_data.get("author", {}).get("login", "")

    reviewer_map: dict[str, dict] = {}

    review_comments = gh_api_paginated(f"repos/{owner}/{repo}/pulls/{pr}/comments")
    for c in review_comments:
        login = c.get("user", {}).get("login", "")
        if not login:
            continue
        user_type = c.get("user", {}).get("type", "User")
        _ensure_reviewer(reviewer_map, login, user_type)
        reviewer_map[login]["review_comments"] += 1

    issue_comments = gh_api_paginated(f"repos/{owner}/{repo}/issues/{pr}/comments")
    for c in issue_comments:
        login = c.get("user", {}).get("login", "")
        if not login:
            continue
        user_type = c.get("user", {}).get("type", "User")
        _ensure_reviewer(reviewer_map, login, user_type)
        reviewer_map[login]["issue_comments"] += 1

    for r in pr_data.get("reviewRequests", []):
        login = r.get("login", "")
        if login:
            _ensure_reviewer(reviewer_map, login, "User")

    for r in pr_data.get("reviews", []):
        login = r.get("author", {}).get("login", "")
        if login:
            is_bot = _is_bot(login, "User")
            _ensure_reviewer(reviewer_map, login, "User")
            reviewer_map[login]["is_bot"] = is_bot

    reviewers = list(reviewer_map.values())
    for r in reviewers:
        r["total_comments"] = r["review_comments"] + r["issue_comments"]

    if args.exclude_bots:
        reviewers = [r for r in reviewers if not r["is_bot"]]
    if args.exclude_author:
        reviewers = [r for r in reviewers if r["login"] != pr_author]

    reviewers.sort(key=lambda r: r["total_comments"], reverse=True)

    bot_count = sum(1 for r in reviewers if r["is_bot"])
    human_count = len(reviewers) - bot_count

    output = {
        "success": True,
        "pull_request": pr,
        "pr_author": pr_author,
        "total_reviewers": len(reviewers),
        "bot_count": bot_count,
        "human_count": human_count,
        "reviewers": reviewers,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
