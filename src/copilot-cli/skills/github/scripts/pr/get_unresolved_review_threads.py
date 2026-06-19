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

Each ``thread`` uses the canonical flat shape produced by
``github_core.api.transform_review_thread`` (``thread_id``, ``is_resolved``,
``path``, ``line``, ``first_comment_*``, ``comments``). It is identical to the
shape emitted by ``get_pr_review_threads.py`` so a consumer can read either
script's ``threads`` without a shape branch. Pass ``--include-comments`` to
materialize the full per-thread comment list; by default ``comments`` is null
and only the ``first_comment_*`` fields are populated.

The ``fetched_pages_complete`` flag is true only when pagination ran to
``hasNextPage == false``. The /pr-review completion gate's pass_when
expression requires this flag to be true alongside ``unresolved_count
== 0``: a partial fetch that happens to return zero unresolved threads
is not evidence that zero unresolved threads exist.

Part of the "Acknowledged vs Resolved" lifecycle model:
NEW -> ACKNOWLEDGED (eyes reaction) -> REPLIED -> RESOLVED (thread marked resolved)

Exit codes follow ADR-035, with one deliberate deviation noted below:
    0 - Snapshot returned (may be incomplete; see ``fetched_pages_complete``)
    2 - Config/usage error (invalid parameters)
    4 - Auth error

API/pagination failures do NOT exit 3. They return 0 with
``success: false`` and ``fetched_pages_complete: false`` so the
/pr-review completion gate's ``pass_when`` (which requires
``fetched_pages_complete == true``) remains the single source of
truth for the verdict. Mixing exit-3 with the JSON-flag contract
would force every consumer to handle two failure surfaces; one
surface is enough.
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
    transform_review_thread,
)

# Safety net: cap pages so a runaway PR cannot pin the script forever.
# 50 pages * 100 threads/page = 5,000 unresolved threads; well past any
# realistic PR. If exceeded, we fall back to fetched_pages_complete=False.
_MAX_PAGES = 50

# Node selection mirrors the fields consumed by
# ``github_core.api.transform_review_thread`` so the emitted ``threads`` share
# the canonical flat shape with get_pr_review_threads.py. ``$commentsLimit`` is
# 1 by default (cheap unresolved-count probe) and 50 under --include-comments.
_QUERY = """\
query($owner: String!, $name: String!, $prNumber: Int!, $commentsLimit: Int!, $cursor: String) {
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
                    isOutdated
                    path
                    line
                    startLine
                    diffSide
                    comments(first: $commentsLimit) {
                        totalCount
                        nodes {
                            databaseId
                            body
                            author { login }
                            createdAt
                        }
                    }
                }
            }
        }
    }
}"""


def fetch_unresolved_threads_paginated(
    owner: str, repo: str, pull_request: int, comments_limit: int = 1,
) -> tuple[list[dict], bool]:
    """Fetch unresolved review threads, paginating to exhaustion.

    Returns a tuple ``(threads, fetched_pages_complete)`` of raw GraphQL
    nodes. ``comments_limit`` is forwarded to the query's
    ``comments(first: ...)`` selection: 1 for the cheap probe, higher when
    the caller wants the full comment list. The flag is True only when the
    underlying GraphQL pagination terminated normally (``hasNextPage`` was
    false on the last page). Pagination errors, page-cap exhaustion, or
    query failures yield False; the caller MUST treat False as "we cannot
    prove there are no more unresolved threads".
    """
    all_unresolved: list[dict] = []
    cursor: str | None = None
    fetched_pages_complete = False

    # ``page_index`` tracks the page count for diagnostic messages. Per
    # Copilot review: the prior implementation used
    # ``len(all_unresolved)`` in the error message, which is the number
    # of threads collected so far, not the page index. They are the same
    # only by coincidence (when each page contains zero or one
    # unresolved thread). An explicit counter avoids the misreport.
    for page_index in range(1, _MAX_PAGES + 1):
        variables: dict = {
            "owner": owner,
            "name": repo,
            "prNumber": pull_request,
            "commentsLimit": comments_limit,
        }
        if cursor:
            variables["cursor"] = cursor

        try:
            data = gh_graphql(_QUERY, variables)
        except RuntimeError as exc:
            print(
                f"Failed to query review threads (page {page_index}): {exc}",
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
    parser.add_argument(
        "--include-comments", action="store_true",
        help="Include the full comment list in each thread (not just the first)",
    )
    parser.add_argument(
        "--output-format", choices=["json", "human", "auto"], default="json",
        help="Accepted for parity; this script always emits JSON (#2684).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.pull_request <= 0:
        error_and_exit("Pull request number must be positive.", 2)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    # Mirror get_pr_review_threads.py: 1 comment for the cheap probe, 50 when
    # the caller wants the whole conversation.
    comments_limit = 50 if args.include_comments else 1

    nodes, fetched_pages_complete = fetch_unresolved_threads_paginated(
        owner, repo, args.pull_request, comments_limit,
    )
    threads = [
        transform_review_thread(node, args.include_comments) for node in nodes
    ]

    # ``success`` reflects whether the *snapshot* is trustworthy. When
    # pagination cannot prove completeness (an underlying GraphQL error
    # or a missing ``endCursor``), the count and threads are at best a
    # lower bound; the dispatcher's pass_when (which requires
    # ``fetched_pages_complete == true``) already fails closed in that
    # case, but emitting ``success: true`` would lie to other consumers.
    output = {
        "success": fetched_pages_complete,
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
