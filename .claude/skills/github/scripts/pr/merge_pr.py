#!/usr/bin/env python3
"""Merge a GitHub Pull Request.

Supports merge, squash, and rebase strategies. Optionally enables auto-merge
or deletes the branch after merge. Idempotent: returns success if already merged.

Exit codes (ADR-035):
    0 = Success (merged or already merged)
    1 = Invalid parameters
    2 = PR not found
    3 = API error
    4 = Not authenticated
    6 = Not mergeable (PR is closed)
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
    gh_graphql,
    resolve_repo_params,
    write_error_and_exit,
)

STATE_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      state
      merged
      mergedAt
      mergedBy { login }
    }
  }
}
"""


def fetch_pr_state(owner: str, repo: str, number: int) -> dict:
    """Fetch the current state of a PR."""
    try:
        data = gh_graphql(STATE_QUERY, {
            "owner": owner,
            "repo": repo,
            "number": number,
        })
    except Exception as e:
        error_msg = str(e)
        if "Could not resolve" in error_msg or "not found" in error_msg:
            write_error_and_exit(f"PR #{number} not found in {owner}/{repo}", 2)
        write_error_and_exit(f"GraphQL query failed: {error_msg}", 3)

    pr: dict | None = data.get("repository", {}).get("pullRequest")
    if not pr:
        write_error_and_exit(f"PR #{number} not found in {owner}/{repo}", 2)
        # write_error_and_exit calls sys.exit; this line is unreachable
        raise SystemExit(2)

    return pr


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge a GitHub Pull Request")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument(
        "--strategy",
        choices=["merge", "squash", "rebase"],
        default="merge",
        help="Merge strategy (default: merge)",
    )
    parser.add_argument("--delete-branch", action="store_true", help="Delete branch after merge")
    parser.add_argument("--auto", action="store_true", help="Enable auto-merge")
    parser.add_argument("--subject", help="Custom merge commit subject")
    parser.add_argument("--body", help="Custom merge commit body")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    pr = fetch_pr_state(owner, repo, args.pull_request)

    if pr.get("merged"):
        merged_by = "unknown"
        if pr.get("mergedBy"):
            merged_by = pr["mergedBy"].get("login", "unknown")
        output = {
            "Success": True,
            "Number": args.pull_request,
            "Strategy": args.strategy,
            "Action": "none",
            "Message": f"PR #{args.pull_request} is already merged by @{merged_by}",
        }
        print(json.dumps(output, indent=2))
        print(f"PR #{args.pull_request} is already merged, no action taken", file=sys.stderr)
        return

    if pr["state"] == "CLOSED":
        output = {
            "Success": False,
            "Number": args.pull_request,
            "Strategy": args.strategy,
            "Action": "none",
            "Message": f"PR #{args.pull_request} is closed and cannot be merged",
        }
        print(json.dumps(output, indent=2))
        write_error_and_exit(f"PR #{args.pull_request} is closed and cannot be merged", 6)

    cmd = ["gh", "pr", "merge", str(args.pull_request), "--repo", f"{owner}/{repo}"]

    strategy_flag = f"--{args.strategy}"
    cmd.append(strategy_flag)

    if args.delete_branch:
        cmd.append("--delete-branch")

    if args.auto:
        cmd.append("--auto")

    if args.subject:
        cmd.extend(["--subject", args.subject])

    if args.body:
        cmd.extend(["--body", args.body])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        write_error_and_exit(f"Failed to merge PR #{args.pull_request}: {result.stderr}", 3)

    action = "auto-merge enabled" if args.auto else "merged"
    output = {
        "Success": True,
        "Number": args.pull_request,
        "Strategy": args.strategy,
        "Action": action,
        "Message": f"PR #{args.pull_request} {action} via {args.strategy}",
    }
    print(json.dumps(output, indent=2))
    print(f"PR #{args.pull_request} {action} ({args.strategy}) in {owner}/{repo}", file=sys.stderr)


if __name__ == "__main__":
    main()
