#!/usr/bin/env python3
"""Resolve PR review threads using GitHub GraphQL API.

Marks review threads as resolved. Required for PRs with branch protection
rules that require all conversations resolved before merging.

Supports single thread resolution or bulk resolution of all unresolved threads.

Exit codes follow ADR-035:
    0 - Success
    1 - Operation failed or invalid parameters
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

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

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_RESOLVE_MUTATION = """\
mutation($threadId: ID!) {
    resolveReviewThread(input: {threadId: $threadId}) {
        thread {
            id
            isResolved
        }
    }
}"""

_THREADS_QUERY = """\
query($owner: String!, $name: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100) {
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes {
                            databaseId
                            author { login }
                        }
                    }
                }
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
                number
            }
        }
    }
}"""


def resolve_review_thread(thread_id: str) -> bool:
    """Resolve a single review thread. Returns True on success."""
    try:
        data = gh_graphql(_RESOLVE_MUTATION, {"threadId": thread_id})
    except RuntimeError as exc:
        print(f"WARNING: Failed to resolve thread {thread_id}: {exc}", file=sys.stderr)
        return False

    thread = data.get("resolveReviewThread", {}).get("thread", {})
    if thread and thread.get("isResolved"):
        return True

    print(f"WARNING: Thread {thread_id} may not have been resolved.", file=sys.stderr)
    return False


def get_unresolved_threads(pr_number: int) -> list[dict[str, Any]]:
    """Fetch unresolved review threads for a PR."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "owner,name"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get repo info: {result.stderr}")

    repo_info = json.loads(result.stdout)
    owner = repo_info["owner"]["login"]
    name = repo_info["name"]

    data = gh_graphql(
        _THREADS_QUERY,
        {"owner": owner, "name": name, "prNumber": pr_number},
    )

    threads = (
        data.get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    return [t for t in threads if not t.get("isResolved", True)]


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
        return "SKIP", "already_resolved"
    return "ACT", "thread_unresolved"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve PR review threads via GitHub GraphQL API.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--thread-id",
        help="GraphQL ID of a single review thread (e.g., PRRT_kwDO...)",
    )
    group.add_argument(
        "--pull-request",
        type=int,
        help="PR number (resolves all unresolved threads when used with --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Resolve all unresolved threads on the PR",
    )
    parser.add_argument(
        "--expected-pull-request",
        type=int,
        help="Expected PR number for single-thread mode.",
    )
    add_output_format_arg(parser)
    return parser


def _resolve_single_thread(args: argparse.Namespace, fmt: str) -> int:
    if args.expected_pull_request is not None and args.expected_pull_request <= 0:
        write_skill_error(
            "Expected pull request number must be positive.",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="resolve_pr_review_thread.py",
        )
        return 2
    decision = _query_single_thread_decision(args, fmt)
    if decision is None:
        return 3
    action, reason = decision
    result = {
        "action": action,
        "reason": reason,
        "thread_id": args.thread_id,
    }
    if action == "SKIP":
        write_skill_output(
            result,
            output_format=fmt,
            human_summary=f"Skipped thread {args.thread_id}: {reason}",
            status="INFO",
            script_name="resolve_pr_review_thread.py",
        )
        return 0
    if not resolve_review_thread(args.thread_id):
        result["reason"] = "resolve_failed"
        write_skill_error(
            f"Failed to resolve thread {args.thread_id}",
            1,
            error_type="VerificationFailed",
            output_format=fmt,
            script_name="resolve_pr_review_thread.py",
            extra=result,
        )
        return 1
    result.update({"reason": "thread_resolved", "success": True})
    write_skill_output(
        result,
        output_format=fmt,
        human_summary=f"Resolved thread {args.thread_id}",
        script_name="resolve_pr_review_thread.py",
    )
    return 0


def _query_single_thread_decision(
    args: argparse.Namespace,
    fmt: str,
) -> tuple[str, str] | None:
    try:
        return _thread_decision(
            args.thread_id,
            args.expected_pull_request,
        )
    except RuntimeError as exc:
        write_skill_error(
            f"Failed to query thread state: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="resolve_pr_review_thread.py",
            extra={
                "action": "SKIP",
                "reason": "thread_state_query_failed",
                "thread_id": args.thread_id,
            },
        )
        return None


def _resolve_cached_thread(
    thread: dict[str, Any],
    expected_pull_request: int,
) -> dict[str, object]:
    thread_id = thread.get("id", "")
    comments = thread.get("comments", {}).get("nodes", [])
    first_comment = comments[0] if comments else {}
    result: dict[str, object] = {
        "thread_id": thread_id,
        "comment_id": first_comment.get("databaseId", "unknown"),
        "author": first_comment.get("author", {}).get("login", "unknown"),
    }
    try:
        action, reason = _thread_decision(thread_id, expected_pull_request)
    except RuntimeError as exc:
        result.update({
            "action": "SKIP",
            "reason": "thread_state_query_failed",
            "error": str(exc),
        })
        return result
    result.update({"action": action, "reason": reason})
    if action == "ACT":
        result["reason"] = (
            "thread_resolved"
            if resolve_review_thread(thread_id)
            else "resolve_failed"
        )
    return result


def _batch_summary(
    unresolved: list[dict[str, Any]],
    pull_request: int,
) -> tuple[dict[str, object], int]:
    results = [
        _resolve_cached_thread(thread, pull_request)
        for thread in unresolved
    ]
    resolved = sum(result["reason"] == "thread_resolved" for result in results)
    skipped = sum(
        result["action"] == "SKIP"
        and result["reason"] != "thread_state_query_failed"
        for result in results
    )
    external_failures = sum(
        result["reason"] == "thread_state_query_failed"
        for result in results
    )
    mutation_failures = sum(
        result["reason"] == "resolve_failed"
        for result in results
    )
    failed = external_failures + mutation_failures
    action = "ACT" if resolved > 0 else "SKIP"
    summary = {
        "action": action,
        "reason": "batch_complete" if failed == 0 else "batch_failed",
        "resolved": resolved,
        "skipped": skipped,
        "failed": failed,
        "total_unresolved": len(unresolved),
        "results": results,
    }
    return summary, 3 if external_failures > 0 else int(mutation_failures > 0)


def _write_batch_result(summary: dict[str, object], code: int, fmt: str) -> int:
    total = int(summary["total_unresolved"])
    resolved = int(summary["resolved"])
    skipped = int(summary["skipped"])
    failed = int(summary["failed"])
    if code == 0:
        write_skill_output(
            summary,
            output_format=fmt,
            human_summary=f"Resolved {resolved} thread(s); skipped {skipped}",
            script_name="resolve_pr_review_thread.py",
        )
        return 0
    error_type = "ApiError" if code == 3 else "VerificationFailed"
    message = (
        "One or more thread state queries failed"
        if code == 3
        else f"Resolved {resolved}/{total} thread(s); {failed} failed"
    )
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=fmt,
        script_name="resolve_pr_review_thread.py",
        extra=summary,
    )
    return code


def _resolve_all_threads(args: argparse.Namespace, fmt: str) -> int:
    try:
        unresolved = get_unresolved_threads(args.pull_request)
    except RuntimeError as exc:
        write_skill_error(
            f"Failed to query unresolved threads: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="resolve_pr_review_thread.py",
        )
        return 3
    if not unresolved:
        summary = {
            "action": "SKIP",
            "reason": "no_unresolved_threads",
            "resolved": 0,
            "skipped": 0,
            "failed": 0,
            "total_unresolved": 0,
            "results": [],
        }
        write_skill_output(
            summary,
            output_format=fmt,
            human_summary="No unresolved review threads found",
            status="INFO",
            script_name="resolve_pr_review_thread.py",
        )
        return 0
    summary, code = _batch_summary(unresolved, args.pull_request)
    return _write_batch_result(summary, code, fmt)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    assert_gh_authenticated()
    if args.thread_id:
        return _resolve_single_thread(args, fmt)
    return _resolve_all_threads(args, fmt)


if __name__ == "__main__":
    raise SystemExit(main())
