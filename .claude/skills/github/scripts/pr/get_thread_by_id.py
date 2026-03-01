#!/usr/bin/env python3
"""Get a single PR review thread by its GraphQL node ID.

Fetches thread metadata and all comments for a specific review thread.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = Thread not found
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
    write_error_and_exit,
)

THREAD_QUERY = """
query($threadId: ID!) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            isOutdated
            path
            line
            comments(first: 100) {
                nodes {
                    id
                    body
                    author { login }
                    createdAt
                }
            }
        }
    }
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Get a PR review thread by GraphQL ID")
    parser.add_argument(
        "--thread-id", required=True,
        help="GraphQL thread ID (must start with PRRT_)",
    )
    args = parser.parse_args()

    if not args.thread_id.startswith("PRRT_"):
        write_error_and_exit(
            f"Invalid thread ID '{args.thread_id}': must start with 'PRRT_'", 1
        )

    assert_gh_authenticated()

    try:
        data = gh_graphql(THREAD_QUERY, {"threadId": args.thread_id})
    except RuntimeError as e:
        write_error_and_exit(f"GraphQL error: {e}", 3)
    except Exception as e:
        write_error_and_exit(f"API request failed: {e}", 3)

    node: dict | None = data.get("node")
    if not node or not node.get("id"):
        write_error_and_exit(f"Thread '{args.thread_id}' not found", 2)
        # write_error_and_exit calls sys.exit; unreachable
        raise SystemExit(2)

    comment_nodes: list[dict] = node.get("comments", {}).get("nodes", [])
    comments = [
        {
            "Id": c["id"],
            "Author": c.get("author", {}).get("login", "unknown"),
            "Body": c.get("body", ""),
            "CreatedAt": c.get("createdAt"),
        }
        for c in comment_nodes
    ]

    output = {
        "Success": True,
        "ThreadId": node["id"],
        "IsResolved": node.get("isResolved", False),
        "IsOutdated": node.get("isOutdated", False),
        "Path": node.get("path"),
        "Line": node.get("line"),
        "Comments": comments,
    }

    print(json.dumps(output, indent=2))
    resolved_label = "resolved" if node.get("isResolved") else "unresolved"
    print(f"Thread {args.thread_id}: {len(comments)} comments, {resolved_label}", file=sys.stderr)


if __name__ == "__main__":
    main()
