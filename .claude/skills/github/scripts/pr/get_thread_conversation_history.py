#!/usr/bin/env python3
"""Get full conversation history of a PR review thread with pagination.

Fetches all comments in a review thread using cursor-based GraphQL pagination.
Optionally includes minimized (hidden) comments.

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

HISTORY_QUERY = """
query($threadId: ID!, $first: Int!, $after: String) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            comments(first: $first, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    body
                    author { login }
                    createdAt
                    isMinimized
                }
            }
        }
    }
}
"""

PAGE_SIZE = 100


def fetch_all_comments(thread_id: str) -> tuple[dict | None, list[dict]]:
    """Fetch all comments for a thread using cursor-based pagination.

    Returns:
        Tuple of (thread metadata dict or None, list of comment dicts).
    """
    all_comments = []
    cursor = None
    thread_meta = None

    while True:
        variables = {"threadId": thread_id, "first": PAGE_SIZE}
        if cursor:
            variables["after"] = cursor

        try:
            data = gh_graphql(HISTORY_QUERY, variables)
        except RuntimeError as e:
            write_error_and_exit(f"GraphQL error: {e}", 3)
        except Exception as e:
            write_error_and_exit(f"API request failed: {e}", 3)

        node = data.get("node")
        if not node or not node.get("id"):
            return None, []

        if thread_meta is None:
            thread_meta = {
                "id": node["id"],
                "isResolved": node.get("isResolved", False),
            }

        comments_data = node.get("comments", {})
        all_comments.extend(comments_data.get("nodes", []))

        page_info = comments_data.get("pageInfo", {})
        if not page_info.get("hasNextPage", False):
            break
        cursor = page_info.get("endCursor")

    return thread_meta, all_comments


def main() -> None:
    parser = argparse.ArgumentParser(description="Get thread conversation history")
    parser.add_argument(
        "--thread-id", required=True,
        help="GraphQL thread ID (must start with PRRT_)",
    )
    parser.add_argument(
        "--include-minimized", action="store_true",
        help="Include minimized/hidden comments",
    )
    args = parser.parse_args()

    if not args.thread_id.startswith("PRRT_"):
        write_error_and_exit(
            f"Invalid thread ID '{args.thread_id}': must start with 'PRRT_'", 1
        )

    assert_gh_authenticated()

    thread_meta, raw_comments = fetch_all_comments(args.thread_id)
    if thread_meta is None:
        write_error_and_exit(f"Thread '{args.thread_id}' not found", 2)

    # Filter minimized unless requested
    if not args.include_minimized:
        raw_comments = [c for c in raw_comments if not c.get("isMinimized", False)]

    comments = [
        {
            "Id": c["id"],
            "Author": c.get("author", {}).get("login", "unknown"),
            "Body": c.get("body", ""),
            "CreatedAt": c.get("createdAt"),
            "IsMinimized": c.get("isMinimized", False),
            "Order": idx + 1,
        }
        for idx, c in enumerate(raw_comments)
    ]

    # thread_meta is guaranteed non-None here; write_error_and_exit
    # calls sys.exit above when thread_meta is None
    assert thread_meta is not None

    output = {
        "Success": True,
        "ThreadId": thread_meta["id"],
        "IsResolved": thread_meta["isResolved"],
        "TotalComments": len(comments),
        "Comments": comments,
    }

    print(json.dumps(output, indent=2))
    resolved_label = "resolved" if thread_meta["isResolved"] else "unresolved"
    print(
        f"Thread {args.thread_id}: {len(comments)} comments, {resolved_label}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
