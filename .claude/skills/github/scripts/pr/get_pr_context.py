#!/usr/bin/env python3
"""Get context and metadata for a GitHub Pull Request.

Retrieves comprehensive PR information including basic metadata,
branch info, labels, reviewers, and optionally diff/changed files.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = Not found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import subprocess
import sys

# Path resolution: supports plugin context (CLAUDE_PLUGIN_ROOT) and local dev
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


def get_pr_context(
    owner: str, repo: str, pr_number: int,
    include_diff: bool = False, include_changed_files: bool = False,
    diff_stat: bool = False,
) -> dict:
    """Fetch PR context from GitHub."""
    fields = (
        "number,title,body,headRefName,baseRefName,state,author,labels,"
        "reviewRequests,commits,additions,deletions,changedFiles,"
        "mergeable,mergedAt,mergedBy,createdAt,updatedAt"
    )
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--repo", f"{owner}/{repo}", "--json", fields],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        if "not found" in result.stderr.lower():
            write_error_and_exit(f"PR #{pr_number} not found in {owner}/{repo}", 2)
        write_error_and_exit(f"Failed to get PR #{pr_number}: {result.stderr}", 3)

    pr = json.loads(result.stdout)

    output = {
        "Success": True,
        "Number": pr["number"],
        "Title": pr["title"],
        "Body": pr.get("body", ""),
        "State": pr["state"],
        "Author": pr.get("author", {}).get("login", ""),
        "HeadBranch": pr["headRefName"],
        "BaseBranch": pr["baseRefName"],
        "Labels": [label["name"] for label in pr.get("labels", [])],
        "Commits": pr.get("commits", {}).get("totalCount", 0),
        "Additions": pr.get("additions", 0),
        "Deletions": pr.get("deletions", 0),
        "ChangedFiles": pr.get("changedFiles", 0),
        "Mergeable": pr.get("mergeable", ""),
        "Merged": bool(pr.get("mergedAt")),
        "MergedBy": pr.get("mergedBy", {}).get("login") if pr.get("mergedBy") else None,
        "CreatedAt": pr.get("createdAt", ""),
        "UpdatedAt": pr.get("updatedAt", ""),
        "Diff": None,
        "Files": None,
        "Owner": owner,
        "Repo": repo,
    }

    if include_diff:
        diff_args = ["gh", "pr", "diff", str(pr_number), "--repo", f"{owner}/{repo}"]
        if diff_stat:
            diff_args.append("--stat")
        diff_result = subprocess.run(diff_args, capture_output=True, text=True)
        if diff_result.returncode == 0:
            output["Diff"] = diff_result.stdout

    if include_changed_files:
        files_result = subprocess.run(
            ["gh", "pr", "diff", str(pr_number), "--repo", f"{owner}/{repo}", "--name-only"],
            capture_output=True, text=True,
        )
        if files_result.returncode == 0:
            output["Files"] = [f for f in files_result.stdout.strip().split("\n") if f.strip()]

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Get PR context and metadata")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument("--include-diff", action="store_true", help="Include PR diff")
    parser.add_argument(
        "--include-changed-files", action="store_true",
        help="Include changed files list",
    )
    parser.add_argument("--diff-stat", action="store_true", help="Use stat format for diff")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    output = get_pr_context(
        resolved["owner"], resolved["repo"], args.pull_request,
        include_diff=args.include_diff,
        include_changed_files=args.include_changed_files,
        diff_stat=args.diff_stat,
    )

    print(json.dumps(output, indent=2))
    print(f"PR #{output['Number']}: {output['Title']}", file=sys.stderr)
    head = output['HeadBranch']
    base = output['BaseBranch']
    state = output['State']
    print(
        f"  Branch: {head} -> {base} | State: {state}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
