#!/usr/bin/env python3
"""Unresolve PR review threads using GitHub GraphQL API.

Marks previously resolved review threads as unresolved (re-opens them).
Counterpart to resolve_pr_review_thread.py.

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

# ---------------------------------------------------------------------------
# GraphQL operations
# ---------------------------------------------------------------------------

_UNRESOLVE_MUTATION = """\
mutation($threadId: ID!) {
    unresolveReviewThread(input: {threadId: $threadId}) {
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


def unresolve_review_thread(thread_id: str) -> bool:
    """Unresolve a single review thread. Returns True on success."""
    try:
        data = gh_graphql(_UNRESOLVE_MUTATION, {"threadId": thread_id})
    except RuntimeError as exc:
        print(
            f"WARNING: Failed to unresolve thread {thread_id}: {exc}",
            file=sys.stderr,
        )
        return False

    thread = data.get("unresolveReviewThread", {}).get("thread")
    if thread is not None and thread.get("isResolved") is False:
        print(f"Unresolved thread: {thread_id}")
        return True

    print(
        f"WARNING: Thread {thread_id} may not have been unresolved.",
        file=sys.stderr,
    )
    return False


def get_resolved_threads(pr_number: int) -> list[dict]:
    """Fetch resolved review threads for a PR."""
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
    return [t for t in threads if t.get("isResolved", False)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unresolve PR review threads via GitHub GraphQL API.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--thread-id",
        help="GraphQL ID of a single review thread (e.g., PRRT_kwDO...)",
    )
    group.add_argument(
        "--pull-request",
        type=int,
        help="PR number (unresolves all resolved threads when used with --all)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Unresolve all resolved threads on the PR",
    )
    return parser


def _validate_thread_id(thread_id: str) -> None:
    """Validate thread ID format."""
    if not thread_id or not thread_id.strip():
        error_and_exit("ThreadId parameter is required.", 1)
    if not thread_id.startswith("PRRT_"):
        error_and_exit("Invalid ThreadId format. Expected PRRT_... format.", 1)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    if args.thread_id:
        _validate_thread_id(args.thread_id)
        success = unresolve_review_thread(args.thread_id)
        result = {
            "Success": success,
            "ThreadId": args.thread_id,
            "Action": "unresolve",
        }
        print(json.dumps(result, indent=2))
        return 0 if success else 1

    # Unresolve all resolved threads
    try:
        resolved_threads = get_resolved_threads(args.pull_request)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    if not resolved_threads:
        print(
            f"No resolved threads on PR #{args.pull_request} to unresolve"
        )
        result = {
            "TotalResolved": 0,
            "Unresolved": 0,
            "Failed": 0,
            "Success": True,
        }
        print(json.dumps(result, indent=2))
        return 0

    print(
        f"Found {len(resolved_threads)} resolved thread(s) "
        f"on PR #{args.pull_request}"
    )

    unresolved_count = 0
    failed_count = 0

    for thread in resolved_threads:
        author = "<unknown>"
        comment_id = "<unknown>"
        comments = thread.get("comments", {}).get("nodes", [])
        if comments and comments[0]:
            first = comments[0]
            if first.get("author", {}).get("login"):
                author = first["author"]["login"]
            if first.get("databaseId"):
                comment_id = first["databaseId"]

        print(
            f"  Unresolving thread {thread['id']} "
            f"(comment {comment_id} by @{author})..."
        )

        if unresolve_review_thread(thread["id"]):
            unresolved_count += 1
        else:
            failed_count += 1

    print()
    print(f"Summary: {unresolved_count} unresolved, {failed_count} failed")

    result = {
        "TotalResolved": len(resolved_threads),
        "Unresolved": unresolved_count,
        "Failed": failed_count,
        "Success": failed_count == 0,
    }
    print(json.dumps(result, indent=2))
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
