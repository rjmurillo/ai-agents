#!/usr/bin/env python3
"""Post a reply to a GitHub PR review comment or top-level PR comment.

Uses the correct endpoint for thread preservation:
- Review comments: Uses in_reply_to for thread context
- Issue comments: Posts to issue comments endpoint for top-level

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = File not found
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Post reply to PR comment")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument("--comment-id", type=int, help="Review comment ID to reply to")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--body", help="Reply text")
    group.add_argument("--body-file", help="Path to file containing reply")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    body = args.body
    if args.body_file:
        if not os.path.exists(args.body_file):
            write_error_and_exit(f"Body file not found: {args.body_file}", 2)
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()

    if not body or not body.strip():
        write_error_and_exit("Body cannot be empty", 1)

    if args.comment_id:
        pr_num = args.pull_request
        cid = args.comment_id
        endpoint = (
            f"repos/{owner}/{repo}/pulls"
            f"/{pr_num}/comments/{cid}/replies"
        )
    else:
        endpoint = f"repos/{owner}/{repo}/issues/{args.pull_request}/comments"

    result = subprocess.run(
        ["gh", "api", endpoint, "-X", "POST", "-f", f"body={body}"],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        write_error_and_exit(f"Failed to post comment: {result.stderr}", 3)

    response = json.loads(result.stdout)

    output = {
        "Success": True,
        "CommentId": response.get("id"),
        "HtmlUrl": response.get("html_url"),
        "PullRequest": args.pull_request,
        "InReplyTo": args.comment_id,
        "CreatedAt": response.get("created_at"),
    }

    print(json.dumps(output, indent=2))
    print(f"Posted reply to PR #{args.pull_request}", file=sys.stderr)
    print(f"  URL: {output['HtmlUrl']}", file=sys.stderr)


if __name__ == "__main__":
    main()
