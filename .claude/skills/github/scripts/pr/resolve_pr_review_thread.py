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
    gh_graphql,
)

# ---------------------------------------------------------------------------
# GraphQL operations
# ---------------------------------------------------------------------------

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


def resolve_review_thread(thread_id: str) -> bool:
    """Resolve a single review thread. Returns True on success."""
    try:
        data = gh_graphql(_RESOLVE_MUTATION, {"threadId": thread_id})
    except RuntimeError as exc:
        print(f"WARNING: Failed to resolve thread {thread_id}: {exc}", file=sys.stderr)
        return False

    thread = (
        data.get("resolveReviewThread", {}).get("thread", {})
    )
    if thread and thread.get("isResolved"):
        print(f"Resolved thread: {thread_id}")
        return True

    print(f"WARNING: Thread {thread_id} may not have been resolved.", file=sys.stderr)
    return False


def get_unresolved_threads(pr_number: int) -> list[dict]:
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    if args.thread_id:
        success = resolve_review_thread(args.thread_id)
        return 0 if success else 1

    # Resolve all unresolved threads
    try:
        unresolved = get_unresolved_threads(args.pull_request)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    if not unresolved:
        print(f"All threads on PR #{args.pull_request} are already resolved")
        result = {
            "TotalUnresolved": 0,
            "Resolved": 0,
            "Failed": 0,
            "Success": True,
        }
        print(json.dumps(result, indent=2))
        return 0

    print(
        f"Found {len(unresolved)} unresolved thread(s) on PR #{args.pull_request}"
    )

    resolved = 0
    failed = 0

    for thread in unresolved:
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
            f"  Resolving thread {thread['id']} "
            f"(comment {comment_id} by @{author})..."
        )

        if resolve_review_thread(thread["id"]):
            resolved += 1
        else:
            failed += 1

    print()
    print(f"Summary: {resolved} resolved, {failed} failed")

    result = {
        "TotalUnresolved": len(unresolved),
        "Resolved": resolved,
        "Failed": failed,
        "Success": failed == 0,
    }
    print(json.dumps(result, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
