#!/usr/bin/env python3
"""Get a single PR review thread by its GraphQL ID.

Retrieves detailed information about a specific review thread using its
GraphQL node ID (e.g., PRRT_kwDOQoWRls5m7ln8).

Uses GraphQL variables for security (prevents injection via ThreadId).

Exit codes follow ADR-035:
    0 - Success
    2 - Config/usage error (invalid parameters)
    3 - External error (API failure, or the thread was not found)
    4 - Auth error
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

from github_core.api import (
    assert_gh_authenticated,
    error_and_exit,
    gh_graphql,
    resolve_repo_params,
)

_QUERY = """\
query($threadId: ID!) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            isOutdated
            path
            line
            startLine
            diffSide
            comments(first: 100) {
                totalCount
                nodes {
                    id
                    databaseId
                    body
                    author { login }
                    createdAt
                    updatedAt
                    isMinimized
                    minimizedReason
                }
            }
        }
    }
}"""


_HELP_EPILOG = """\
examples:
  %(prog)s --thread-id PRRT_kwDOExample

exit codes:
  0  success
  2  config/usage error (invalid parameters)
  3  external error (API failure, or the thread was not found)
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get a single PR review thread by its GraphQL ID.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--thread-id",
        required=True,
        help="GraphQL node ID of the review thread (PRRT_...)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.thread_id.strip():
        error_and_exit("ThreadId parameter is required.", 2)

    if not args.thread_id.startswith("PRRT_"):
        error_and_exit("Invalid ThreadId format. Expected PRRT_... format.", 2)

    assert_gh_authenticated()
    resolve_repo_params(args.owner, args.repo)

    try:
        data = gh_graphql(_QUERY, {"threadId": args.thread_id})
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg or "not found" in msg:
            error_and_exit(f"Thread {args.thread_id} not found.", 3)
        error_and_exit(f"Failed to query thread: {msg}", 3)

    thread = data.get("node")
    if not thread or not thread.get("id"):
        error_and_exit(
            f"Thread {args.thread_id} not found or is not a review thread.",
            3,
        )

    comments_data = thread.get("comments", {})
    comments_nodes = comments_data.get("nodes", [])

    comments = [
        {
            "id": c.get("databaseId"),
            "node_id": c.get("id"),
            "author": c.get("author", {}).get("login") if c.get("author") else None,
            "body": c.get("body"),
            "created_at": c.get("createdAt"),
            "updated_at": c.get("updatedAt"),
            "is_minimized": c.get("isMinimized"),
            "minimized_reason": c.get("minimizedReason"),
        }
        for c in comments_nodes
    ]

    output = {
        "success": True,
        "thread_id": thread.get("id"),
        "is_resolved": thread.get("isResolved"),
        "is_outdated": thread.get("isOutdated"),
        "path": thread.get("path"),
        "line": thread.get("line"),
        "start_line": thread.get("startLine"),
        "diff_side": thread.get("diffSide"),
        "comment_count": comments_data.get("totalCount", 0),
        "comments": comments,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
