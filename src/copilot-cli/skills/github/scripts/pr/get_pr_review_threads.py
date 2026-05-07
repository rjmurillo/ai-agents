#!/usr/bin/env python3
"""Get all review threads for a GitHub Pull Request.

Retrieves review threads with their resolution status, comments,
and thread IDs needed for resolve/reply operations.

Complements get_unresolved_review_threads by providing thread-level
context rather than just unresolved threads.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings

logger = logging.getLogger(__name__)

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

# Page size for the reviewThreads connection. GitHub GraphQL caps connection
# pages at 100; we ask for 100 and iterate until pageInfo.hasNextPage is false.
# The PR #1887 retrospective records that the earlier first:100 single-page
# query masked 6+ unresolved threads twice in that cycle, because the script
# silently truncated on PRs whose thread count crossed the page boundary.
_THREADS_PAGE_SIZE = 100

# Safety bound: a PR with more than 5000 review threads is almost certainly
# either a runaway state or a query targeting the wrong PR. We exit the loop
# rather than spin forever. When the loop exits by cap, we emit a
# warnings.warn and surface a `pagination_truncated: true` field in the JSON
# output so a caller cannot mistake "5000 threads" for "complete result".
# The PR #1887 retrospective records that a silent first:100 truncation hid
# 6+ unresolved threads; a silent at-cap truncation would reproduce the same
# false-zero failure class.
_MAX_THREAD_PAGES = 50

_THREADS_QUERY = """\
query($owner: String!, $repo: String!, $prNumber: Int!, $commentsLimit: Int!, $cursor: String) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100, after: $cursor) {
                totalCount
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
                            id
                            databaseId
                            body
                            author { login }
                            createdAt
                            updatedAt
                        }
                    }
                }
            }
        }
    }
}"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get all review threads for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--unresolved-only", action="store_true",
        help="Return only unresolved threads",
    )
    parser.add_argument(
        "--include-comments", action="store_true",
        help="Include all comments in each thread (not just first)",
    )
    return parser


def _run_threads_query(
    owner: str, repo: str, pr: int, comments_limit: int,
    cursor: str | None = None,
) -> dict:
    """Execute the parameterized GraphQL query for one page of review threads.

    The `cursor` argument is the GraphQL cursor returned by the previous page's
    `pageInfo.endCursor`. On the first call it is None; the query treats a None
    `$cursor` as "from the start". Callers iterate via `_collect_all_threads`.
    """
    variables = {
        "owner": owner,
        "repo": repo,
        "prNumber": pr,
        "commentsLimit": comments_limit,
    }
    if cursor is not None:
        variables["cursor"] = cursor
    return gh_graphql(_THREADS_QUERY, variables)


def _extract_review_threads(
    data: dict, owner: str, repo: str, pr: int, pages_seen: int,
) -> dict | None:
    """Pull the reviewThreads dict from a GraphQL response, defensively.

    Returns the reviewThreads object on success, ``None`` when any of the
    intermediate fields is missing. Each missing-field branch logs a
    distinct ``op=review_threads_failed reason=...`` line so an operator
    grepping the failure surface can distinguish the failure mode without
    reading source.
    """
    repository = data.get("repository") or {}
    pull_request_obj = repository.get("pullRequest")
    if pull_request_obj is None:
        logger.warning(
            "op=review_threads_failed pr=%d owner=%s repo=%s page=%d "
            "reason=pr_not_found",
            pr, owner, repo, pages_seen,
        )
        return None
    review_threads = pull_request_obj.get("reviewThreads")
    if review_threads is None:
        logger.warning(
            "op=review_threads_failed pr=%d owner=%s repo=%s page=%d "
            "reason=field_missing",
            pr, owner, repo, pages_seen,
        )
        return None
    if review_threads.get("nodes") is None:
        logger.warning(
            "op=review_threads_failed pr=%d owner=%s repo=%s page=%d "
            "reason=nodes_missing",
            pr, owner, repo, pages_seen,
        )
        return None
    return review_threads


def _log_pagination_progress(
    pr: int, pages_seen: int, cursor_in: str | None,
    page_info: dict, page_nodes: list, aggregated_count: int,
) -> None:
    """Emit the per-page DEBUG line. Full cursor is logged so adjacent
    pages with shared 8-char prefixes can be distinguished by an operator
    inspecting DEBUG output.
    """
    logger.debug(
        "op=review_threads_page pr=%d page=%d cursor_in=%s end_cursor=%s "
        "nodes=%d cumulative=%d has_next=%s",
        pr,
        pages_seen,
        cursor_in if cursor_in else "<start>",
        page_info.get("endCursor"),
        len(page_nodes),
        aggregated_count,
        bool(page_info.get("hasNextPage")),
    )


def _collect_all_threads(
    owner: str, repo: str, pr: int, comments_limit: int,
) -> tuple[list[dict] | None, int, bool]:
    """Page through all reviewThreads for a PR.

    Returns a tuple ``(nodes, total_count, truncated)``.

    Return contract:
    - ``nodes is None`` means the PR was not found, or its reviewThreads
      connection was missing from the GraphQL response. Distinguish via
      the ``op=review_threads_failed reason=...`` log line.
    - ``nodes == []`` means the PR exists and has zero review threads.
    - ``truncated is True`` means the loop exited at ``_MAX_THREAD_PAGES``
      (5000-thread ceiling) while ``hasNextPage`` was still true; triggers
      ``warnings.warn``.

    Raises RuntimeError on transport failures, propagated from gh_graphql.
    """
    aggregated: list[dict] = []
    total_count = 0
    cursor: str | None = None
    pages_seen = 0

    while pages_seen < _MAX_THREAD_PAGES:
        pages_seen += 1
        data = _run_threads_query(owner, repo, pr, comments_limit, cursor)
        review_threads = _extract_review_threads(data, owner, repo, pr, pages_seen)
        if review_threads is None:
            return None, 0, False

        page_nodes = review_threads.get("nodes", [])
        aggregated.extend(page_nodes)
        total_count = review_threads.get("totalCount", total_count)

        page_info = review_threads.get("pageInfo") or {}
        _log_pagination_progress(
            pr, pages_seen, cursor, page_info, page_nodes, len(aggregated),
        )

        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break
    else:
        # while-else fires when pages_seen reaches the cap without a break.
        # The last-seen page reported hasNextPage=true; surface it.
        warnings.warn(
            f"Hit _MAX_THREAD_PAGES={_MAX_THREAD_PAGES} for PR #{pr}; "
            f"result truncated at {len(aggregated)} threads "
            f"(reported total_count={total_count}). "
            f"Re-run with a higher cap or paginate caller-side.",
            stacklevel=2,
        )
        return aggregated, total_count, True

    return aggregated, total_count, False


def _transform_thread(thread: dict, include_comments: bool) -> dict:
    """Transform a raw GraphQL thread node into the output format."""
    comments_nodes = thread.get("comments", {}).get("nodes", [])
    first = comments_nodes[0] if comments_nodes else None

    result: dict = {
        "thread_id": thread.get("id"),
        "is_resolved": thread.get("isResolved", False),
        "is_outdated": thread.get("isOutdated", False),
        "path": thread.get("path"),
        "line": thread.get("line"),
        "start_line": thread.get("startLine"),
        "diff_side": thread.get("diffSide"),
        "comment_count": thread.get("comments", {}).get("totalCount", 0),
        "first_comment_id": first.get("databaseId") if first else None,
        "first_comment_author": (
            first.get("author", {}).get("login") if first and first.get("author") else None
        ),
        "first_comment_body": first.get("body") if first else None,
        "first_comment_created_at": first.get("createdAt") if first else None,
        "comments": None,
    }

    if include_comments:
        result["comments"] = [
            {
                "id": c.get("databaseId"),
                "author": c.get("author", {}).get("login") if c.get("author") else None,
                "body": c.get("body"),
                "created_at": c.get("createdAt"),
            }
            for c in comments_nodes
        ]

    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request

    comments_limit = 50 if args.include_comments else 1

    try:
        threads, _total_count, truncated = _collect_all_threads(
            owner, repo, pr, comments_limit,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg:
            error_and_exit(f"PR #{pr} not found in {owner}/{repo}", 2)
        error_and_exit(f"Failed to query review threads: {msg}", 3)

    if threads is None:
        error_and_exit(f"PR #{pr} not found or has no review threads", 2)

    if args.unresolved_only:
        threads = [t for t in threads if not t.get("isResolved", True)]

    transformed = [_transform_thread(t, args.include_comments) for t in threads]

    total = len(threads)
    unresolved = sum(1 for t in threads if not t.get("isResolved", True))

    output = {
        "success": True,
        "pull_request": pr,
        "owner": owner,
        "repo": repo,
        "total_threads": total,
        "resolved_count": total - unresolved,
        "unresolved_count": unresolved,
        "pagination_truncated": truncated,
        "threads": transformed,
    }
    # Truncation is signaled to consumers via two channels:
    # - `pagination_truncated: bool` field in JSON output (machine-readable)
    # - `warnings.warn` emitted by `_collect_all_threads` (human-readable on
    #   stderr). Python's default warnings filter prints UserWarning to
    #   stderr at most once per call site; CI pipelines reading stderr for
    #   diagnostics see the warning without our adding a second print line.
    # No second `print(WARNING ...)` here: duplicate stderr output would
    # confuse callers parsing for a single signal.

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
