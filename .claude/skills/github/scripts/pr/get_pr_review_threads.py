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
import os
import subprocess
import sys

_WORKSPACE = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")),
)
sys.path.insert(0, _WORKSPACE)

from scripts.github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
)


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


def _build_query(owner: str, repo: str, pr: int, comments_limit: int) -> str:
    """Build the GraphQL query with inline values.

    The original PS1 script inlined owner/repo/pr into the query string.
    We replicate that here for fidelity.
    """
    return f"""\
query {{
    repository(owner: "{owner}", name: "{repo}") {{
        pullRequest(number: {pr}) {{
            reviewThreads(first: 100) {{
                totalCount
                nodes {{
                    id
                    isResolved
                    isOutdated
                    path
                    line
                    startLine
                    diffSide
                    comments(first: {comments_limit}) {{
                        totalCount
                        nodes {{
                            id
                            databaseId
                            body
                            author {{ login }}
                            createdAt
                            updatedAt
                        }}
                    }}
                }}
            }}
        }}
    }}
}}"""


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
    owner, repo = resolved["Owner"], resolved["Repo"]
    pr = args.pull_request

    comments_limit = 50 if args.include_comments else 1
    query = _build_query(owner, repo, pr, comments_limit)

    result = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        err_msg = result.stderr or result.stdout
        if "Could not resolve" in err_msg:
            error_and_exit(f"PR #{pr} not found in {owner}/{repo}", 2)
        error_and_exit(f"Failed to query review threads: {err_msg}", 3)

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        error_and_exit(f"Failed to parse GraphQL response: {result.stdout}", 3)

    threads = (
        parsed.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes")
    )

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
        "threads": transformed,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
