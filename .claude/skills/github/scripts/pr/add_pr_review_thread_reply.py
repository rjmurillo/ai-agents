#!/usr/bin/env python3
"""Add a reply to a GitHub PR review thread using GraphQL.

Posts a reply to a review thread using the thread ID (PRRT_...) rather than
comment ID. Required for proper thread management with branch protection rules.

Optionally resolves the thread after posting the reply. When resolving, the
script disables any armed auto-merge on the owning PR before the reply and
resolve mutations. That closes the race where resolving the final thread lets
GitHub merge before the completion gate runs.

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
from typing import Any, cast

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    error_and_exit,
    gh_graphql,
)
from github_core.validation import inline_body_error

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

_DISABLE_AUTO_MERGE_MUTATION = """\
mutation($pullRequestId: ID!) {
    disablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId}) {
        pullRequest {
            id
            number
            autoMergeRequest {
                enabledAt
            }
        }
    }
}"""

_THREAD_QUERY = """\
query($threadId: ID!) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            pullRequest {
                id
                number
                autoMergeRequest {
                    enabledAt
                    mergeMethod
                }
            }
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
        from github_core.validation import assert_valid_body_file

        assert_valid_body_file(args.body_file)
        return Path(args.body_file).read_text(encoding="utf-8")
    return str(args.body)


def query_thread_state(thread_id: str) -> dict[str, Any] | None:
    data = gh_graphql(_THREAD_QUERY, {"threadId": thread_id})
    node = data.get("node")
    return node if isinstance(node, dict) else None


def _thread_is_actionable(thread_id: str) -> bool:
    return _actionable_thread_state(thread_id) is not None


def _actionable_thread_state(thread_id: str) -> dict[str, Any] | None:
    try:
        thread = query_thread_state(thread_id)
    except RuntimeError as exc:
        error_and_exit(f"Failed to query thread state: {exc}", 3)
    if thread is None:
        print(json.dumps({"action": "SKIP", "reason": "not_found"}, indent=2))
        return None
    if thread.get("isResolved"):
        print(json.dumps({"action": "SKIP", "reason": "thread_resolved"}, indent=2))
        return None
    return thread


def _disable_armed_auto_merge_before_resolve(thread: dict[str, Any]) -> bool:
    """Disable armed auto-merge before resolving a review thread.

    Resolving the final thread can satisfy branch protection and fire an
    already-armed auto-merge before the completion gate runs. Disarm first;
    if that fails, do not post the reply or resolve the thread.
    """
    pull_request = thread.get("pullRequest")
    if not isinstance(pull_request, dict):
        return False
    if pull_request.get("autoMergeRequest") is None:
        return False

    pull_request_id = pull_request.get("id")
    if not isinstance(pull_request_id, str) or not pull_request_id:
        error_and_exit(
            "Thread belongs to an armed auto-merge PR, but the PR node id is missing",
            3,
        )

    try:
        data = gh_graphql(
            _DISABLE_AUTO_MERGE_MUTATION,
            {"pullRequestId": pull_request_id},
        )
    except RuntimeError as exc:
        pr_number = pull_request.get("number", "unknown")
        error_and_exit(
            f"Failed to disable auto-merge for PR #{pr_number} before resolving "
            f"thread: {exc}",
            3,
        )

    auto_merge = (
        data.get("disablePullRequestAutoMerge", {})
        .get("pullRequest", {})
        .get("autoMergeRequest")
    )
    if auto_merge is not None:
        pr_number = pull_request.get("number", "unknown")
        error_and_exit(
            f"Auto-merge remains armed for PR #{pr_number}; refusing to resolve thread",
            3,
        )
    return True


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.thread_id.startswith("PRRT_"):
        error_and_exit("Invalid ThreadId format. Expected PRRT_... format.", 2)

    body = _resolve_body(args)
    body_error = inline_body_error(body)
    if body_error:
        error_and_exit(body_error, 2)

    assert_gh_authenticated()

    thread = _actionable_thread_state(args.thread_id)
    if thread is None:
        return 0

    auto_merge_disabled = False
    if args.resolve:
        auto_merge_disabled = _disable_armed_auto_merge_before_resolve(thread)

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

    comment_value = (reply_data.get("addPullRequestReviewThreadReply") or {}).get("comment")
    if not isinstance(comment_value, dict):
        error_and_exit("Reply may not have been posted successfully", 3)
    comment = cast(dict[str, Any], comment_value)

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
        "action": "ACT",
        "success": True,
        "thread_id": args.thread_id,
        "comment_id": comment.get("databaseId"),
        "comment_node_id": comment.get("id"),
        "html_url": comment.get("url"),
        "created_at": comment.get("createdAt"),
        "author": author.get("login") if author else None,
        "thread_resolved": thread_resolved,
        "auto_merge_disabled_before_resolve": auto_merge_disabled,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
