#!/usr/bin/env python3
"""Close a GitHub Pull Request.

Idempotent: returns success if the PR is already closed or merged.
Optionally posts a comment before closing.

Exit codes (ADR-035):
    0 = Success (closed or already closed/merged)
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
    gh_graphql,
    resolve_repo_params,
    write_error_and_exit,
)
from github_core.validation import test_safe_file_path

STATE_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      state
      merged
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
        # write_error_and_exit calls sys.exit; unreachable
        raise SystemExit(2)

    return pr


def close_pr(owner: str, repo: str, number: int, comment: str | None) -> None:
    """Close a PR using gh CLI."""
    cmd = ["gh", "pr", "close", str(number), "--repo", f"{owner}/{repo}"]
    if comment:
        cmd.extend(["--comment", comment])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        write_error_and_exit(f"Failed to close PR #{number}: {result.stderr}", 3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Close a GitHub Pull Request")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    comment_group = parser.add_mutually_exclusive_group()
    comment_group.add_argument("--comment", help="Comment to post before closing")
    comment_group.add_argument("--comment-file", help="Path to file containing comment")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    comment = args.comment
    if args.comment_file:
        if not test_safe_file_path(args.comment_file):
            write_error_and_exit(f"Path traversal attempt detected: {args.comment_file}", 1)
        if not os.path.exists(args.comment_file):
            write_error_and_exit(f"Comment file not found: {args.comment_file}", 1)
        with open(args.comment_file, encoding="utf-8") as f:
            comment = f.read()

    pr = fetch_pr_state(owner, repo, args.pull_request)
    state = pr["state"]
    merged = pr.get("merged", False)

    if merged:
        output = {
            "Success": True,
            "Number": args.pull_request,
            "State": "MERGED",
            "Action": "none",
            "Message": f"PR #{args.pull_request} is already merged",
        }
        print(json.dumps(output, indent=2))
        print(f"PR #{args.pull_request} is already merged, no action taken", file=sys.stderr)
        return

    if state == "CLOSED":
        output = {
            "Success": True,
            "Number": args.pull_request,
            "State": "CLOSED",
            "Action": "none",
            "Message": f"PR #{args.pull_request} is already closed",
        }
        print(json.dumps(output, indent=2))
        print(f"PR #{args.pull_request} is already closed, no action taken", file=sys.stderr)
        return

    close_pr(owner, repo, args.pull_request, comment)

    output = {
        "Success": True,
        "Number": args.pull_request,
        "State": "CLOSED",
        "Action": "closed",
        "Message": f"PR #{args.pull_request} closed successfully",
    }
    print(json.dumps(output, indent=2))
    print(f"Closed PR #{args.pull_request} in {owner}/{repo}", file=sys.stderr)


if __name__ == "__main__":
    main()
