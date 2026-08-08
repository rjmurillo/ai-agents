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
import os
import sys
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
    sys.exit(2)

_script_dir = os.path.dirname(__file__)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from auto_merge_guard import guard_auto_merge_before_final_thread_resolution
from github_core.api import (
    assert_gh_authenticated,
    error_and_exit,
    gh_graphql,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
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

_THREAD_QUERY = """\
query($threadId: ID!) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            pullRequest {
                number
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
    parser.add_argument(
        "--pull-request",
        type=int,
        help="Expected PR number. Threads from another PR are skipped.",
    )

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Reply text (inline)")
    body_group.add_argument("--body-file", help="Path to file containing reply")
    add_output_format_arg(parser)
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


def _thread_decision(
    thread_id: str,
    expected_pull_request: int | None,
) -> tuple[str, str]:
    thread = query_thread_state(thread_id)
    if thread is None:
        return "SKIP", "not_found"
    pull_request = thread.get("pullRequest")
    actual_pull_request = (
        pull_request.get("number")
        if isinstance(pull_request, dict)
        else None
    )
    if (
        expected_pull_request is not None
        and actual_pull_request != expected_pull_request
    ):
        return "SKIP", "wrong_pull_request"
    if thread.get("isResolved"):
        return "SKIP", "thread_resolved"
    return "ACT", "thread_unresolved"


def _guard_auto_merge_before_resolution(thread_id: str) -> dict[str, Any]:
    try:
        return guard_auto_merge_before_final_thread_resolution(thread_id)
    except RuntimeError as exc:
        error_and_exit(
            "Thread reply posted but auto-merge guard failed; "
            f"thread left unresolved: {exc}",
            3,
        )
        raise AssertionError("error_and_exit returned") from exc


def _resolve_thread_after_reply(thread_id: str) -> bool:
    resolve_data = gh_graphql(
        _RESOLVE_MUTATION,
        {"threadId": thread_id},
    )
    return bool(
        resolve_data
        .get("resolveReviewThread", {})
        .get("thread", {})
        .get("isResolved", False)
    )


def _initial_thread_gate(args: argparse.Namespace, fmt: str) -> int | None:
    try:
        action, reason = _thread_decision(args.thread_id, args.pull_request)
    except RuntimeError as exc:
        write_skill_error(
            f"Failed to query thread state: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="add_pr_review_thread_reply.py",
            extra={
                "action": "SKIP",
                "reason": "thread_state_query_failed",
                "thread_id": args.thread_id,
            },
        )
        return 3
    if action == "ACT":
        return None
    write_skill_output(
        {
            "action": action,
            "reason": reason,
            "thread_id": args.thread_id,
        },
        output_format=fmt,
        human_summary=f"Skipped thread {args.thread_id}: {reason}",
        status="INFO",
        script_name="add_pr_review_thread_reply.py",
    )
    return 0


def _post_reply(
    thread_id: str,
    body: str,
    fmt: str,
) -> tuple[dict[str, Any] | None, int]:
    try:
        reply_data = gh_graphql(
            _REPLY_MUTATION,
            {"threadId": thread_id, "body": body},
        )
    except RuntimeError as exc:
        write_skill_error(
            f"Failed to post thread reply: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="add_pr_review_thread_reply.py",
            extra={
                "action": "ACT",
                "reason": "reply_failed",
                "thread_id": thread_id,
            },
        )
        return None, 3

    comment_value = (reply_data.get("addPullRequestReviewThreadReply") or {}).get("comment")
    if isinstance(comment_value, dict):
        return cast(dict[str, Any], comment_value), 0
    write_skill_error(
        "Reply may not have been posted successfully",
        3,
        error_type="ApiError",
        output_format=fmt,
        script_name="add_pr_review_thread_reply.py",
        extra={
            "action": "ACT",
            "reason": "reply_result_missing",
            "thread_id": thread_id,
        },
    )
    return None, 3


def _resolve_after_reply(
    args: argparse.Namespace,
    comment: dict[str, Any],
    fmt: str,
) -> tuple[dict[str, object], int]:
    if not args.resolve:
        return {
            "thread_resolved": False,
            "resolve_action": "SKIP",
            "resolve_reason": "not_requested",
        }, 0
    try:
        action, reason = _thread_decision(args.thread_id, args.pull_request)
    except RuntimeError as exc:
        return _resolve_reply_error(
            f"Reply posted but failed to requery thread before resolve: {exc}",
            3,
            "ApiError",
            "resolve_state_query_failed",
            args,
            comment,
            fmt,
        )
    if action == "SKIP":
        return {
            "thread_resolved": reason == "thread_resolved",
            "resolve_action": action,
            "resolve_reason": reason,
        }, 0

    auto_merge_guard = _guard_auto_merge_before_resolution(args.thread_id)
    try:
        thread_resolved = _resolve_thread_after_reply(args.thread_id)
    except RuntimeError as exc:
        return _resolve_reply_error(
            f"Reply posted but failed to resolve thread: {exc}",
            3,
            "ApiError",
            "resolve_failed",
            args,
            comment,
            fmt,
        )
    if thread_resolved:
        return {
            "thread_resolved": True,
            "resolve_action": "ACT",
            "resolve_reason": "thread_resolved",
            "auto_merge_guard": auto_merge_guard,
        }, 0
    return _resolve_reply_error(
        "Reply posted but the thread remains unresolved",
        1,
        "VerificationFailed",
        "resolve_not_confirmed",
        args,
        comment,
        fmt,
    )


def _resolve_reply_error(
    message: str,
    code: int,
    error_type: str,
    reason: str,
    args: argparse.Namespace,
    comment: dict[str, Any],
    fmt: str,
) -> tuple[dict[str, object], int]:
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=fmt,
        script_name="add_pr_review_thread_reply.py",
        extra={
            "action": "ACT",
            "reason": reason,
            "thread_id": args.thread_id,
            "comment_id": comment.get("databaseId"),
        },
    )
    return {}, code


def _validate_args(args: argparse.Namespace) -> str:
    if not args.thread_id.startswith("PRRT_"):
        error_and_exit("Invalid ThreadId format. Expected PRRT_... format.", 2)
    if args.pull_request is not None and args.pull_request <= 0:
        error_and_exit("Pull request number must be positive.", 2)
    body = _resolve_body(args)
    body_error = inline_body_error(body)
    if body_error:
        error_and_exit(body_error, 2)
    return body


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    body = _validate_args(args)
    assert_gh_authenticated()

    gate_code = _initial_thread_gate(args, fmt)
    if gate_code is not None:
        return gate_code
    comment, post_code = _post_reply(args.thread_id, body, fmt)
    if comment is None:
        return post_code
    resolution, resolution_code = _resolve_after_reply(args, comment, fmt)
    if resolution_code != 0:
        return resolution_code
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
        **resolution,
    }
    write_skill_output(
        output,
        output_format=fmt,
        human_summary=f"Replied to thread {args.thread_id}",
        script_name="add_pr_review_thread_reply.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
