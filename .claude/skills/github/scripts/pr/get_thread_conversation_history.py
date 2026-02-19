#!/usr/bin/env python3
"""Get the full conversation history of a PR review thread.

Retrieves all comments in a review thread with detailed metadata.
Supports pagination for threads with many comments.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters
    2 - Thread not found
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
)

# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------

_THREAD_QUERY = """\
query($threadId: ID!, $first: Int!, $after: String) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            isOutdated
            path
            line
            startLine
            diffSide
            comments(first: $first, after: $after) {
                totalCount
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    databaseId
                    body
                    author { login }
                    createdAt
                    updatedAt
                    isMinimized
                    minimizedReason
                    replyTo { databaseId }
                }
            }
        }
    }
}"""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def fetch_thread_comments(thread_id: str) -> tuple[dict, list[dict]]:
    """Fetch all comments for a thread with pagination.

    Returns (thread_info, all_comments).
    """
    all_comments: list[dict] = []
    page_size = 100
    cursor: str | None = None
    thread_info: dict | None = None

    while True:
        # Build gh api graphql command
        gh_args = [
            "gh", "api", "graphql",
            "-f", f"query={_THREAD_QUERY}",
            "-f", f"threadId={thread_id}",
            "-F", f"first={page_size}",
        ]
        if cursor:
            gh_args.extend(["-f", f"after={cursor}"])

        result = subprocess.run(
            gh_args,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            error_text = result.stderr.strip() or result.stdout.strip()
            if "Could not resolve" in error_text or "not found" in error_text:
                error_and_exit(f"Thread {thread_id} not found.", 2)
            error_and_exit(f"Failed to query thread: {error_text}", 3)

        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            error_and_exit(f"Failed to parse GraphQL response: {result.stdout}", 3)

        node = parsed.get("data", {}).get("node")
        if node is None or node.get("id") is None:
            error_and_exit(
                f"Thread {thread_id} not found or is not a review thread.", 2,
            )

        # Store thread info from first page
        if thread_info is None:
            thread_info = {
                "ThreadId": node["id"],
                "IsResolved": node.get("isResolved", False),
                "IsOutdated": node.get("isOutdated", False),
                "Path": node.get("path"),
                "Line": node.get("line"),
                "StartLine": node.get("startLine"),
                "DiffSide": node.get("diffSide"),
                "TotalComments": node.get("comments", {}).get("totalCount", 0),
            }

        # Add comments from this page
        comments = node.get("comments", {})
        for comment in comments.get("nodes", []):
            all_comments.append(comment)

        page_info = comments.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    return thread_info or {}, all_comments


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get the full conversation history of a PR review thread.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--thread-id", required=True,
        help="GraphQL node ID of the review thread (PRRT_... format)",
    )
    parser.add_argument(
        "--include-minimized", action="store_true",
        help="Include minimized (hidden) comments in output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Validate thread ID format
    if not args.thread_id or not args.thread_id.strip():
        error_and_exit("ThreadId parameter is required.", 1)
    if not args.thread_id.startswith("PRRT_"):
        error_and_exit("Invalid ThreadId format. Expected PRRT_... format.", 1)

    assert_gh_authenticated()

    # Resolve repo (for consistency, though not used by the thread query)
    resolve_repo_params(args.owner, args.repo)

    thread_info, all_comments = fetch_thread_comments(args.thread_id)

    # Filter minimized comments
    if not args.include_minimized:
        filtered = [c for c in all_comments if not c.get("isMinimized", False)]
    else:
        filtered = list(all_comments)

    # Transform to output format with sequence numbers
    output_comments: list[dict] = []
    for seq, comment in enumerate(filtered, 1):
        output_comments.append({
            "Sequence": seq,
            "Id": comment.get("databaseId"),
            "NodeId": comment.get("id"),
            "Author": comment.get("author", {}).get("login") if comment.get("author") else None,
            "Body": comment.get("body", ""),
            "CreatedAt": comment.get("createdAt"),
            "UpdatedAt": comment.get("updatedAt"),
            "IsMinimized": comment.get("isMinimized", False),
            "MinimizedReason": comment.get("minimizedReason"),
            "ReplyToId": (
                comment.get("replyTo", {}).get("databaseId")
                if comment.get("replyTo") else None
            ),
        })

    # Console summary
    status = "Resolved" if thread_info.get("IsResolved") else "Unresolved"
    outdated = " (Outdated)" if thread_info.get("IsOutdated") else ""
    print(f"Thread Conversation: {args.thread_id}", file=sys.stderr)
    print(f"  Status: {status}{outdated}", file=sys.stderr)
    print(f"  Path: {thread_info.get('Path')}", file=sys.stderr)
    print(f"  Line: {thread_info.get('Line')}", file=sys.stderr)
    print(f"  Total Comments: {thread_info.get('TotalComments')}", file=sys.stderr)

    if not args.include_minimized:
        minimized_count = len(all_comments) - len(output_comments)
        if minimized_count > 0:
            print(
                f"  Hidden (minimized): {minimized_count} "
                f"(use --include-minimized to show)",
                file=sys.stderr,
            )

    # Brief conversation preview
    print("", file=sys.stderr)
    print("Conversation:", file=sys.stderr)
    for c in output_comments[:5]:
        body = c["Body"] or ""
        preview = body[:60] + "..." if len(body) > 60 else body
        preview = preview.replace("\n", " ").replace("\r", "")
        print(f"  [{c['Sequence']}] @{c['Author']}: {preview}", file=sys.stderr)
    if len(output_comments) > 5:
        print(
            f"  ... and {len(output_comments) - 5} more comment(s)",
            file=sys.stderr,
        )

    # Structured output
    output = {
        "Success": True,
        "ThreadId": thread_info.get("ThreadId"),
        "IsResolved": thread_info.get("IsResolved", False),
        "IsOutdated": thread_info.get("IsOutdated", False),
        "Path": thread_info.get("Path"),
        "Line": thread_info.get("Line"),
        "StartLine": thread_info.get("StartLine"),
        "DiffSide": thread_info.get("DiffSide"),
        "TotalComments": thread_info.get("TotalComments", 0),
        "ReturnedComments": len(output_comments),
        "MinimizedExcluded": (
            len(all_comments) - len(output_comments)
            if not args.include_minimized else 0
        ),
        "Comments": output_comments,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
