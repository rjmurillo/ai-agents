#!/usr/bin/env python3
"""Add a reply to a GitHub PR review thread using GraphQL.

Posts a reply to a review thread using the thread ID (PRRT_...) rather than
comment ID. Required for proper thread management with branch protection rules.

Optionally resolves the thread after posting the reply.

Exit codes follow ADR-035:
    0 - Success
    2 - Config/usage error (invalid parameters, file not found)
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

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
    gh_graphql,
)

_REPLY_MUTATION = """\
mutation($threadId: ID!, $body: String!) {
    addPullRequestReviewThreadReply(input: {pullRequestReviewThreadId: $threadId, body: $body}) {
        comment {
            id
            databaseId
            url
            createdAt
            author {
                login
            }
        }
    }
}"""

_RESOLVE_MUTATION = """\
mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
        thread {
            id
            isResolved
        }
    }
}"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add a reply to a PR review thread via GraphQL.",
    )
    parser.add_argument(
        "--thread-id", required=True,
        help="GraphQL thread ID (e.g., PRRT_kwDOQoWRls5m3L76)",
    )
    parser.add_argument(
        "--resolve", action="store_true",
        help="Resolve the thread after posting the reply",
    )

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Reply text (inline)")
    body_group.add_argument("--body-file", help="Path to file containing reply")
    return parser


def _resolve_body(args: argparse.Namespace) -> str:
    if args.body_file:
        resolved = Path(args.body_file).resolve()
        if ".." in Path(args.body_file).parts:
            error_and_exit(f"Path traversal detected: {args.body_file}", 2)
        if not resolved.is_file():
            error_and_exit(f"Body file not found: {args.body_file}", 2)
        return resolved.read_text(encoding="utf-8")
    return str(args.body)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.thread_id.startswith("PRRT_"):
        error_and_exit("Invalid ThreadId format. Expected PRRT_... format.", 2)

    body = _resolve_body(args)
    if not body or not body.strip():
        error_and_exit("Body cannot be empty.", 2)

    assert_gh_authenticated()

    try:
        reply_data = gh_graphql(
            _REPLY_MUTATION,
            {"threadId": args.thread_id, "body": body},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg:
            error_and_exit(f"Thread {args.thread_id} not found", 2)
        error_and_exit(f"Failed to post thread reply: {msg}", 3)

    comment = (reply_data.get("addPullRequestReviewThreadReply") or {}).get("comment")
    if not comment:
        error_and_exit("Reply may not have been posted successfully", 3)

    thread_resolved = False
    if args.resolve:
        try:
            resolve_data = gh_graphql(
                _RESOLVE_MUTATION,
                {"threadId": args.thread_id},
            )
            thread_resolved = (
                resolve_data
                .get("resolveReviewThread", {})
                .get("thread", {})
                .get("isResolved", False)
            )
        except RuntimeError as exc:
            warnings.warn(
                f"Thread reply posted but failed to resolve: {exc}",
                stacklevel=2,
            )

    author = comment.get("author")
    output = {
        "success": True,
        "thread_id": args.thread_id,
        "comment_id": comment.get("databaseId"),
        "comment_node_id": comment.get("id"),
        "html_url": comment.get("url"),
        "created_at": comment.get("createdAt"),
        "author": author.get("login") if author else None,
        "thread_resolved": thread_resolved,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
