#!/usr/bin/env python3
"""Check if a GitHub Pull Request has been merged.

Uses GraphQL API (source of truth) to determine PR merge state.
Use before starting PR review work to prevent wasted effort on merged PRs.

Exit codes:
    0 = PR is NOT merged (safe to proceed with review)
    1 = PR IS merged (skip review work)
    2 = Error occurred (not found or API failure)
    4 = Not authenticated
"""

import argparse
import json
import os
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
    write_error_and_exit,
)

QUERY = """
query($owner: String!, $repo: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      state
      merged
      mergedAt
      mergedBy { login }
    }
  }
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Check if a PR has been merged")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    try:
        data = gh_graphql(QUERY, {
            "owner": resolved["owner"],
            "repo": resolved["repo"],
            "prNumber": args.pull_request,
        })
    except Exception as e:
        write_error_and_exit(f"GraphQL query failed: {e}", 2)

    pr = data.get("repository", {}).get("pullRequest")
    if not pr:
        write_error_and_exit(
            f"PR #{args.pull_request} not found in {resolved['owner']}/{resolved['repo']}",
            2,
        )

    output = {
        "Success": True,
        "PullRequest": args.pull_request,
        "Owner": resolved["owner"],
        "Repo": resolved["repo"],
        "State": pr["state"],
        "Merged": pr["merged"],
        "MergedAt": pr.get("mergedAt"),
        "MergedBy": pr.get("mergedBy", {}).get("login") if pr.get("mergedBy") else None,
    }

    print(json.dumps(output, indent=2))

    pr_num = args.pull_request
    if pr["merged"]:
        if pr.get("mergedBy"):
            merged_by = pr["mergedBy"].get("login", "automated process")
        else:
            merged_by = "automated process"
        merged_at = pr['mergedAt']
        print(
            f"[MERGED] PR #{pr_num} merged"
            f" at {merged_at} by @{merged_by}",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        state = pr['state']
        print(
            f"[NOT MERGED] PR #{pr_num}"
            f" is not merged (state: {state})",
            file=sys.stderr,
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
