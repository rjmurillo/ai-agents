#!/usr/bin/env python3
"""Unresolve PR review threads using GitHub GraphQL API.

Marks resolved review threads as unresolved. Useful for reopening
conversations that were prematurely resolved.

Exit codes (ADR-035):
    0 = Success (all threads unresolved)
    1 = Invalid parameters or partial failure
    2 = PR not found
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
    resolve_repo_params,
    write_error_and_exit,
)

UNRESOLVE_MUTATION = """
mutation($threadId: ID!) {
    unresolveReviewThread(input: {threadId: $threadId}) {
        thread { id isResolved }
    }
}
"""

RESOLVED_THREADS_QUERY = """
query($owner: String!, $repo: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100) {
                nodes {
                    id
                    isResolved
                }
            }
        }
    }
}
"""


def unresolve_thread(thread_id: str) -> bool:
    """Unresolve a single review thread. Returns True on success."""
    try:
        data = gh_graphql(UNRESOLVE_MUTATION, {"threadId": thread_id})
        thread = data.get("unresolveReviewThread", {}).get("thread", {})
        unresolved = not thread.get("isResolved", True)
        if unresolved:
            print(f"Unresolved thread: {thread_id}", file=sys.stderr)
        else:
            print(f"Warning: Thread {thread_id} may still be resolved", file=sys.stderr)
        return unresolved
    except Exception as e:
        print(f"Warning: Failed to unresolve thread {thread_id}: {e}", file=sys.stderr)
        return False


def get_resolved_threads(owner: str, repo: str, pr_number: int) -> list[dict]:
    """Fetch all resolved review threads for a PR."""
    try:
        data = gh_graphql(RESOLVED_THREADS_QUERY, {
            "owner": owner,
            "repo": repo,
            "prNumber": pr_number,
        })
    except Exception as e:
        error_msg = str(e)
        if "Could not resolve" in error_msg:
            write_error_and_exit(f"PR #{pr_number} not found", 2)
        write_error_and_exit(f"Failed to query threads: {error_msg}", 3)

    pr = data.get("repository", {}).get("pullRequest")
    if not pr:
        write_error_and_exit(f"PR #{pr_number} not found", 2)

    all_threads = pr.get("reviewThreads", {}).get("nodes", [])
    return [t for t in all_threads if t.get("isResolved", False)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Unresolve PR review thread(s)")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument(
        "--thread-id",
        help="Single thread ID to unresolve (PRRT_ prefix)",
    )
    parser.add_argument("--pull-request", type=int, help="PR number (use with --all)")
    parser.add_argument(
        "--all", action="store_true",
        help="Unresolve all resolved threads on the PR",
    )
    args = parser.parse_args()

    if not args.thread_id and not args.pull_request:
        write_error_and_exit("Provide --thread-id or --pull-request with --all", 1)

    if args.thread_id and not args.thread_id.startswith("PRRT_"):
        write_error_and_exit("Thread ID must start with 'PRRT_'", 1)

    if args.all and not args.pull_request:
        write_error_and_exit("--all requires --pull-request", 1)

    assert_gh_authenticated()

    # Single thread mode
    if args.thread_id and not args.all:
        success = unresolve_thread(args.thread_id)
        output = {
            "Success": success,
            "UnresolvedCount": 1 if success else 0,
            "Threads": [{
                "Id": args.thread_id,
                "WasResolved": success,
            }],
        }
        print(json.dumps(output, indent=2))
        sys.exit(0 if success else 1)

    # Bulk mode: unresolve all resolved threads on a PR
    resolved = resolve_repo_params(args.owner, args.repo)
    resolved_threads = get_resolved_threads(resolved["owner"], resolved["repo"], args.pull_request)

    if not resolved_threads:
        output = {
            "Success": True,
            "UnresolvedCount": 0,
            "Threads": [],
        }
        print(json.dumps(output, indent=2))
        print(f"No resolved threads on PR #{args.pull_request}", file=sys.stderr)
        sys.exit(0)

    thread_count = len(resolved_threads)
    print(
        f"Found {thread_count} resolved thread(s)"
        f" on PR #{args.pull_request}",
        file=sys.stderr,
    )

    threads_result = []
    success_count = 0
    fail_count = 0

    for thread in resolved_threads:
        tid = thread["id"]
        if unresolve_thread(tid):
            success_count += 1
            threads_result.append({"Id": tid, "WasResolved": True})
        else:
            fail_count += 1
            threads_result.append({"Id": tid, "WasResolved": False})

    output = {
        "Success": fail_count == 0,
        "UnresolvedCount": success_count,
        "Threads": threads_result,
    }

    print(json.dumps(output, indent=2))
    print(f"Summary: {success_count} unresolved, {fail_count} failed", file=sys.stderr)
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
