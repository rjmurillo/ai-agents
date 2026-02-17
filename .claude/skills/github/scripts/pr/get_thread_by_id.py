#!/usr/bin/env python3
"""Get a single PR review thread by its GraphQL ID.

Retrieves detailed information about a specific review thread using its
GraphQL node ID (e.g., PRRT_kwDOQoWRls5m7ln8).

Uses GraphQL variables for security (prevents injection via ThreadId).

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Thread not found
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib"))
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get a single PR review thread by its GraphQL ID.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--thread-id", required=True,
        help="GraphQL node ID of the review thread (PRRT_...)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.thread_id.strip():
        error_and_exit("ThreadId parameter is required.", 1)

    if not args.thread_id.startswith("PRRT_"):
        error_and_exit("Invalid ThreadId format. Expected PRRT_... format.", 1)

    assert_gh_authenticated()
    resolve_repo_params(args.owner, args.repo)

    try:
        data = gh_graphql(_QUERY, {"threadId": args.thread_id})
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg or "not found" in msg:
            error_and_exit(f"Thread {args.thread_id} not found.", 2)
        error_and_exit(f"Failed to query thread: {msg}", 3)

    thread = data.get("node")
    if not thread or not thread.get("id"):
        error_and_exit(
            f"Thread {args.thread_id} not found or is not a review thread.", 2,
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
