#!/usr/bin/env python3
"""Unresolve PR review threads using GitHub GraphQL API.

Marks previously resolved review threads as unresolved (re-opens them).
Counterpart to resolve_pr_review_thread.py.

Exit codes follow ADR-035:
    0 - Success
    1 - Operation failed (unresolve returned error)
    2 - Config/usage error (invalid parameters)
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

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
query($owner: String!, $name: String!, $prNumber: Int!, $cursor: String) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
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


_MAX_PAGES = 50


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

    resolved: list[dict] = []
    cursor = ""
    for _ in range(_MAX_PAGES):
        variables: dict = {"owner": owner, "name": name, "prNumber": pr_number}
        if cursor:
            variables["cursor"] = cursor
        data = gh_graphql(_THREADS_QUERY, variables)
        threads = data.get("repository", {}).get("pullRequest", {}).get("reviewThreads", {})
        resolved.extend(t for t in threads.get("nodes", []) if t.get("isResolved", False))
        page_info = threads.get("pageInfo") or {}
        if not page_info.get("hasNextPage", False):
            return resolved
        cursor = page_info.get("endCursor") or ""
        if not cursor:
            raise RuntimeError(
                f"review thread pagination on PR #{pr_number} returned no cursor; "
                f"read {len(resolved)} resolved thread(s) before it stopped"
            )
    raise RuntimeError(
        f"review thread pagination on PR #{pr_number} exceeded {_MAX_PAGES} pages; "
        f"read {len(resolved)} resolved thread(s) before it stopped"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


_HELP_EPILOG = """\
examples:
  %(prog)s --thread-id PRRT_kwDOExample
  %(prog)s --pull-request 123 --all

exit codes:
  0  success
  1  operation failed (unresolve returned error)
  2  config/usage error (invalid parameters)
  3  API error
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unresolve PR review threads via GitHub GraphQL API.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--thread-id",
        help="GraphQL ID of a single review thread (e.g., PRRT_kwDO...)",
    )
    group.add_argument(
        "--pull-request",
        type=int,
        help="PR number. Requires --all, which unresolves every resolved thread on the PR",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Unresolve all resolved threads on the PR (required with --pull-request)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the threads that would be unresolved; unresolve nothing",
    )
    return parser


def _validate_scope_flags(args: argparse.Namespace) -> None:
    """Require --all for the bulk mode and refuse it for a single thread."""
    if args.pull_request is not None and not args.all:
        error_and_exit(
            "--pull-request unresolves every resolved thread on the PR and needs "
            "--all. Expected: --pull-request N --all, or --thread-id PRRT_...",
            2,
        )
    if args.thread_id and args.all:
        error_and_exit(
            "--all applies to --pull-request only. Expected: --thread-id PRRT_... "
            "alone, or --pull-request N --all",
            2,
        )


def _validate_thread_id(thread_id: str) -> None:
    """Validate thread ID format."""
    if not thread_id or not thread_id.strip():
        error_and_exit("ThreadId parameter is required.", 2)
    if not thread_id.startswith("PRRT_"):
        error_and_exit("Invalid ThreadId format. Expected PRRT_... format.", 2)


_THREAD_QUERY = """\
query($threadId: ID!) {
    node(id: $threadId) {
        ... on PullRequestReviewThread { id isResolved }
    }
}"""


def _preview_single(thread_id: str) -> int:
    """Read the thread and report the plan; exit 1 where a real run's mutation would fail."""
    try:
        data = gh_graphql(_THREAD_QUERY, {"threadId": thread_id})
    except RuntimeError as exc:
        print(f"WARNING: Could not read thread {thread_id}: {exc}", file=sys.stderr)
        data = {}
    node = data.get("node")
    found = isinstance(node, dict) and node.get("id") == thread_id
    result: dict[str, object] = {
        "Success": found,
        "ThreadId": thread_id,
        "Action": "would_unresolve",
        "DryRun": True,
    }
    if found:
        result["AlreadyUnresolved"] = node.get("isResolved") is False
    else:
        print(f"WARNING: Thread {thread_id} not found or not readable.", file=sys.stderr)
    print(json.dumps(result, indent=2))
    return 0 if found else 1


def _unresolve_single(args: argparse.Namespace) -> int:
    """Unresolve one thread, or report the plan under --dry-run."""
    _validate_thread_id(args.thread_id)
    if args.dry_run:
        return _preview_single(args.thread_id)
    success = unresolve_review_thread(args.thread_id)
    result = {
        "Success": success,
        "ThreadId": args.thread_id,
        "Action": "unresolve",
    }
    print(json.dumps(result, indent=2))
    return 0 if success else 1


def _report_nothing_resolved(args: argparse.Namespace) -> int:
    """Report a PR with no resolved threads; under --dry-run the result carries the marker."""
    print(f"No resolved threads on PR #{args.pull_request} to unresolve", file=sys.stderr)
    result: dict[str, object] = {
        "TotalResolved": 0,
        "Unresolved": 0,
        "Failed": 0,
        "Success": True,
    }
    if args.dry_run:
        result["DryRun"] = True
    print(json.dumps(result, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_scope_flags(args)
    assert_gh_authenticated()

    if args.thread_id:
        return _unresolve_single(args)

    # Unresolve all resolved threads
    try:
        resolved_threads = get_resolved_threads(args.pull_request)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    if not resolved_threads:
        return _report_nothing_resolved(args)

    print(
        f"Found {len(resolved_threads)} resolved thread(s) on PR #{args.pull_request}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "Success": True,
                    "Action": "would_unresolve",
                    "DryRun": True,
                    "TotalResolved": len(resolved_threads),
                    "ThreadIds": [t["id"] for t in resolved_threads],
                },
                indent=2,
            )
        )
        return 0

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
            f"  Unresolving thread {thread['id']} (comment {comment_id} by @{author})...",
            file=sys.stderr,
        )

        if unresolve_review_thread(thread["id"]):
            unresolved_count += 1
        else:
            failed_count += 1

    print(f"Summary: {unresolved_count} unresolved, {failed_count} failed", file=sys.stderr)

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
