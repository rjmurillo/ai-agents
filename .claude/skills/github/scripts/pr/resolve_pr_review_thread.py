#!/usr/bin/env python3
"""Resolve PR review threads using GitHub GraphQL API.

Marks review threads as resolved. Required for PRs with branch
protection rules that require all conversations to be resolved.

Exit codes (ADR-035):
    0 = Success (all threads resolved)
    1 = One or more threads failed to resolve
    2 = PR not found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import subprocess
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

RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) {
    thread { id isResolved }
  }
}
"""

THREADS_QUERY = """
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
}
"""


def resolve_thread(thread_id: str) -> bool:
    """Resolve a single review thread. Returns True on success."""
    try:
        data = gh_graphql(RESOLVE_MUTATION, {"threadId": thread_id})
        resolve_data = data.get("resolveReviewThread", {})
        resolved: bool = resolve_data.get("thread", {}).get("isResolved", False)
        if resolved:
            print(f"Resolved thread: {thread_id}", file=sys.stderr)
        else:
            print(f"Warning: Thread {thread_id} may not have been resolved", file=sys.stderr)
        return resolved
    except Exception as e:
        print(f"Warning: Failed to resolve thread {thread_id}: {e}", file=sys.stderr)
        return False


def get_unresolved_threads(pr_number: int) -> list[dict]:
    """Get unresolved review threads for a PR."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "owner,name"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        write_error_and_exit(f"Failed to get repo info: {result.stderr}", 3)

    repo_info = json.loads(result.stdout)
    owner = repo_info["owner"]["login"]
    name = repo_info["name"]

    try:
        data = gh_graphql(THREADS_QUERY, {
            "owner": owner, "name": name, "prNumber": pr_number,
        })
    except Exception as e:
        write_error_and_exit(f"Failed to query threads: {e}", 3)

    pr_data = data.get("repository", {}).get("pullRequest", {})
    all_threads = pr_data.get("reviewThreads", {}).get("nodes", [])
    return [t for t in all_threads if not t.get("isResolved", False)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve PR review thread(s)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--thread-id", help="Single thread ID to resolve")
    group.add_argument("--pull-request", type=int, help="PR number (with --all)")
    parser.add_argument("--all", action="store_true", help="Resolve all unresolved threads")
    args = parser.parse_args()

    assert_gh_authenticated()

    if args.thread_id:
        success = resolve_thread(args.thread_id)
        sys.exit(0 if success else 1)
    else:
        if not args.all:
            write_error_and_exit("Use --all with --pull-request to resolve all threads", 1)

        unresolved = get_unresolved_threads(args.pull_request)

        if not unresolved:
            print(f"All threads on PR #{args.pull_request} are already resolved", file=sys.stderr)
            sys.exit(0)

        print(
            f"Found {len(unresolved)} unresolved thread(s) "
            f"on PR #{args.pull_request}",
            file=sys.stderr,
        )

        resolved_count = 0
        failed_count = 0

        for thread in unresolved:
            comments = thread.get("comments", {}).get("nodes", [])
            first = comments[0] if comments else {}
            author_data = first.get("author")
            author = author_data.get("login", "<unknown>") if author_data else "<unknown>"
            cid = first.get("databaseId", "<unknown>")

            tid = thread['id']
            print(
                f"  Resolving thread {tid} (comment {cid} by @{author})...",
                file=sys.stderr,
            )

            if resolve_thread(thread["id"]):
                resolved_count += 1
            else:
                failed_count += 1

        output = {
            "TotalUnresolved": len(unresolved),
            "Resolved": resolved_count,
            "Failed": failed_count,
            "Success": failed_count == 0,
        }
        print(json.dumps(output, indent=2))
        print(f"\nSummary: {resolved_count} resolved, {failed_count} failed", file=sys.stderr)
        sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
