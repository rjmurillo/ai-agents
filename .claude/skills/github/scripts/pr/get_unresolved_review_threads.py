#!/usr/bin/env python3
"""Get unresolved review threads for a GitHub Pull Request.

Uses GitHub GraphQL API to query review thread resolution status.
Paginates ``reviewThreads`` to exhaustion so a 100-thread cliff cannot
silently mask unresolved threads (this masking failure was documented
in retrospective 2026-05-05-pr-1887-iteration-paradox.md).

Output is a JSON object with:

    {
      "success": true,
      "pull_request": <int>,
      "unresolved_count": <int>,
      "fetched_pages_complete": <bool>,
      "threads": [<thread>, ...]
    }

The ``fetched_pages_complete`` flag is true only when pagination ran to
``hasNextPage == false``. The /pr-review completion gate's pass_when
expression requires this flag to be true alongside ``unresolved_count
== 0``: a partial fetch that happens to return zero unresolved threads
is not evidence that zero unresolved threads exist.

Part of the "Acknowledged vs Resolved" lifecycle model:
NEW -> ACKNOWLEDGED (eyes reaction) -> REPLIED -> RESOLVED (thread marked resolved)

Exit codes follow ADR-035:
    0 - Success
    2 - Config/usage error (invalid parameters)
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
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
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    gh_graphql,
    resolve_repo_params,
)

# Safety net: cap pages so a runaway PR cannot pin the script forever.
# 50 pages * 100 threads/page = 5,000 unresolved threads; well past any
# realistic PR. If exceeded, we fall back to fetched_pages_complete=False.
_MAX_PAGES = 50

_QUERY = """\
query($owner: String!, $name: String!, $prNumber: Int!, $cursor: String) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes {
                            databaseId
                        }
                    }
                }
            }
        }
    }
}"""


def fetch_unresolved_threads_paginated(
    owner: str, repo: str, pull_request: int,
) -> tuple[list[dict], bool]:
    """Fetch unresolved review threads, paginating to exhaustion.

    Returns a tuple ``(threads, fetched_pages_complete)``. The flag is
    True only when the underlying GraphQL pagination terminated normally
    (``hasNextPage`` was false on the last page). Pagination errors,
    page-cap exhaustion, or query failures yield False; the caller MUST
    treat False as "we cannot prove there are no more unresolved
    threads".
    """
    all_unresolved: list[dict] = []
    cursor: str | None = None
    fetched_pages_complete = False

    for _ in range(_MAX_PAGES):
        variables: dict = {
            "owner": owner,
            "name": repo,
            "prNumber": pull_request,
        }
        if cursor:
            variables["cursor"] = cursor

        try:
            data = gh_graphql(_QUERY, variables)
        except RuntimeError as exc:
            print(
                f"Failed to query review threads (page {len(all_unresolved)}+): {exc}",
                file=sys.stderr,
            )
            return all_unresolved, False

        repo_data = data.get("repository") or {}
        pr_data = repo_data.get("pullRequest")
        if pr_data is None:
            return all_unresolved, False
        review_threads = pr_data.get("reviewThreads")
        if review_threads is None:
            return all_unresolved, False

        nodes = review_threads.get("nodes", []) or []
        for node in nodes:
            if not node.get("isResolved", True):
                all_unresolved.append(node)

        page_info = review_threads.get("pageInfo", {}) or {}
        if not page_info.get("hasNextPage", False):
            fetched_pages_complete = True
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            # hasNextPage was true but no cursor; treat as incomplete.
            return all_unresolved, False

    return all_unresolved, fetched_pages_complete


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get unresolved review threads for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.pull_request <= 0:
        error_and_exit("Pull request number must be positive.", 2)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    threads, fetched_pages_complete = fetch_unresolved_threads_paginated(
        owner, repo, args.pull_request,
    )

    output = {
        "success": True,
        "pull_request": args.pull_request,
        "owner": owner,
        "repo": repo,
        "unresolved_count": len(threads),
        "fetched_pages_complete": fetched_pages_complete,
        "threads": threads,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
