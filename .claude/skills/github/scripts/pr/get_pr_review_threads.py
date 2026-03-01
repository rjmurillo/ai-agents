#!/usr/bin/env python3
"""Get all review threads for a GitHub Pull Request.

Retrieves review threads with resolution status, comments, and thread IDs
needed for resolve_pr_review_thread.py.

Exit codes (ADR-035):
    0 = Success
    2 = Not found
    3 = API error
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
query($owner: String!, $repo: String!, $prNumber: Int!, $commentsLimit: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $prNumber) {
      reviewThreads(first: 100) {
        totalCount
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          startLine
          diffSide
          comments(first: $commentsLimit) {
            totalCount
            nodes {
              id
              databaseId
              body
              author { login }
              createdAt
              updatedAt
            }
          }
        }
      }
    }
  }
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Get PR review threads")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument(
        "--unresolved-only", action="store_true",
        help="Only return unresolved threads",
    )
    parser.add_argument(
        "--include-comments", action="store_true",
        help="Include all comments per thread",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    comments_limit = 50 if args.include_comments else 1

    try:
        data = gh_graphql(QUERY, {
            "owner": resolved["owner"],
            "repo": resolved["repo"],
            "prNumber": args.pull_request,
            "commentsLimit": comments_limit,
        })
    except Exception as e:
        error_msg = str(e)
        if "Could not resolve" in error_msg:
            owner = resolved['owner']
            repo = resolved['repo']
            pr_num = args.pull_request
            write_error_and_exit(
                f"PR #{pr_num} not found in {owner}/{repo}",
                2,
            )
        write_error_and_exit(f"Failed to query review threads: {error_msg}", 3)

    pr_data = data.get("repository", {}).get("pullRequest")
    if not pr_data:
        write_error_and_exit(f"PR #{args.pull_request} not found", 2)

    threads = pr_data.get("reviewThreads", {}).get("nodes", [])

    if args.unresolved_only:
        threads = [t for t in threads if not t.get("isResolved", False)]

    output_threads = []
    for thread in threads:
        comments = thread.get("comments", {}).get("nodes", [])
        first_comment = comments[0] if comments else None

        thread_data = {
            "ThreadId": thread["id"],
            "IsResolved": thread.get("isResolved", False),
            "IsOutdated": thread.get("isOutdated", False),
            "Path": thread.get("path"),
            "Line": thread.get("line"),
            "StartLine": thread.get("startLine"),
            "DiffSide": thread.get("diffSide"),
            "CommentCount": thread.get("comments", {}).get("totalCount", 0),
            "FirstCommentId": first_comment.get("databaseId") if first_comment else None,
            "FirstCommentAuthor": (
                first_comment.get("author", {}).get("login")
                if first_comment and first_comment.get("author")
                else None
            ),
            "FirstCommentBody": first_comment.get("body") if first_comment else None,
            "FirstCommentCreatedAt": first_comment.get("createdAt") if first_comment else None,
        }

        if args.include_comments:
            thread_data["Comments"] = [
                {
                    "Id": c.get("databaseId"),
                    "Author": c.get("author", {}).get("login") if c.get("author") else None,
                    "Body": c.get("body"),
                    "CreatedAt": c.get("createdAt"),
                }
                for c in comments
            ]

        output_threads.append(thread_data)

    total_count = len(threads)
    unresolved_count = sum(
        1 for t in threads
        if not t.get("IsResolved", t.get("isResolved", False))
    )
    resolved_count = total_count - unresolved_count

    output = {
        "Success": True,
        "PullRequest": args.pull_request,
        "Owner": resolved["owner"],
        "Repo": resolved["repo"],
        "TotalThreads": total_count,
        "ResolvedCount": resolved_count,
        "UnresolvedCount": unresolved_count,
        "Threads": output_threads,
    }

    print(json.dumps(output, indent=2))
    print(f"PR #{args.pull_request} Review Threads:", file=sys.stderr)
    print(
        f"  Total: {total_count}"
        f" | Resolved: {resolved_count}"
        f" | Unresolved: {unresolved_count}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
