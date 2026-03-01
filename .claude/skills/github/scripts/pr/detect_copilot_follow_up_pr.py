#!/usr/bin/env python3
"""Detect Copilot follow-up PR patterns for a given Pull Request.

Searches for PRs with branch names matching the copilot/sub-pr-{N} pattern,
then categorizes each as DUPLICATE, SUPPLEMENTAL, or INDEPENDENT.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = Original PR not found
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


def get_original_pr(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch the original PR info for comparison."""
    result = subprocess.run(
        [
            "gh", "pr", "view", str(pr_number),
            "--repo", f"{owner}/{repo}",
            "--json", "number,title,state,headRefName,baseRefName,body",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if "not found" in result.stderr.lower() or "Could not resolve" in result.stderr:
            write_error_and_exit(f"PR #{pr_number} not found in {owner}/{repo}", 2)
        write_error_and_exit(f"Failed to fetch PR #{pr_number}: {result.stderr}", 3)
    pr_data: dict = json.loads(result.stdout)
    return pr_data


def find_follow_ups(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Search for PRs with copilot follow-up branch pattern."""
    head_pattern = f"copilot/sub-pr-{pr_number}"
    result = subprocess.run(
        [
            "gh", "pr", "list",
            "--head", head_pattern,
            "--repo", f"{owner}/{repo}",
            "--json", "number,title,state,headRefName,baseRefName,body",
            "--state", "all",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        write_error_and_exit(f"Failed to search follow-up PRs: {result.stderr}", 3)
    follow_ups: list[dict] = json.loads(result.stdout)
    return follow_ups


def titles_match(title_a: str, title_b: str) -> bool:
    """Check if two PR titles are substantially similar."""
    return title_a.strip().lower() == title_b.strip().lower()


def bodies_similar(body_a: str | None, body_b: str | None) -> bool:
    """Check if two PR bodies share significant overlap."""
    if not body_a or not body_b:
        return False
    a_words = set(body_a.lower().split())
    b_words = set(body_b.lower().split())
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words)
    smaller = min(len(a_words), len(b_words))
    return (overlap / smaller) > 0.7 if smaller > 0 else False


def categorize(follow_up: dict, original: dict) -> str:
    """Categorize a follow-up PR relative to the original.

    DUPLICATE: Same title or very similar body to the original.
    SUPPLEMENTAL: Targets the original PR's head branch.
    INDEPENDENT: Targets main/master or another base.
    """
    if titles_match(follow_up.get("title", ""), original.get("title", "")):
        return "DUPLICATE"
    if bodies_similar(follow_up.get("body"), original.get("body")):
        return "DUPLICATE"
    if follow_up.get("baseRefName") == original.get("headRefName"):
        return "SUPPLEMENTAL"
    return "INDEPENDENT"


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect Copilot follow-up PR patterns")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pr-number", type=int, required=True, help="Original PR number")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved["owner"]
    repo = resolved["repo"]

    original = get_original_pr(owner, repo, args.pr_number)
    follow_ups_raw = find_follow_ups(owner, repo, args.pr_number)

    follow_ups = []
    for fu in follow_ups_raw:
        category = categorize(fu, original)
        follow_ups.append({
            "Number": fu.get("number"),
            "Title": fu.get("title"),
            "State": fu.get("state"),
            "Category": category,
            "HeadBranch": fu.get("headRefName"),
            "BaseBranch": fu.get("baseRefName"),
        })

    output = {
        "Success": True,
        "OriginalPR": args.pr_number,
        "FollowUps": follow_ups,
        "TotalFollowUps": len(follow_ups),
    }

    print(json.dumps(output, indent=2))

    print(f"PR #{args.pr_number}: found {len(follow_ups)} Copilot follow-up(s)", file=sys.stderr)
    for fu in follow_ups:
        num, cat = fu['Number'], fu['Category']
        print(f"  #{num} [{cat}] {fu['Title']} ({fu['State']})", file=sys.stderr)


if __name__ == "__main__":
    main()
