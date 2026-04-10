#!/usr/bin/env python3
"""Detect PR review comments on files that no longer exist at PR HEAD.

When bot reviewers comment on multi-commit PRs, earlier comments may reference
files that were deleted or replaced in later commits.  This script identifies
those stale comments so they can be resolved or ignored.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error
    2 - Configuration error (plugin lib not found)
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

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
    gh_api_paginated,
    gh_graphql,
    resolve_repo_params,
)

# ---------------------------------------------------------------------------
# GraphQL: fetch all review threads with path and line info
# ---------------------------------------------------------------------------

_REVIEW_THREADS_QUERY = """\
query($owner: String!, $name: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100) {
                nodes {
                    id
                    isResolved
                    path
                    line
                    comments(first: 1) {
                        nodes {
                            author {
                                login
                            }
                        }
                    }
                }
            }
        }
    }
}"""


def fetch_review_threads(
    owner: str, repo: str, pr_number: int,
) -> list[dict[str, Any]]:
    """Fetch all review threads for a PR via GraphQL.

    Returns a list of thread dicts with id, path, line, and author info.

    Raises:
        RuntimeError: On GraphQL transport or response errors.
    """
    data = gh_graphql(
        _REVIEW_THREADS_QUERY,
        {"owner": owner, "name": repo, "prNumber": pr_number},
    )
    threads = (
        data.get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    return threads if threads else []


def fetch_pr_files(owner: str, repo: str, pr_number: int) -> set[str]:
    """Fetch the set of file paths present in the PR at HEAD.

    Uses the GitHub REST API to get the file list.
    Excludes files with status 'removed' since they do not exist at HEAD.
    """
    raw_files = gh_api_paginated(
        f"repos/{owner}/{repo}/pulls/{pr_number}/files"
    )
    return {
        f.get("filename", "")
        for f in raw_files
        if f.get("filename") and f.get("status") != "removed"
    }


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def detect_stale_comments(
    owner: str, repo: str, pr_number: int,
) -> dict[str, Any]:
    """Detect review comments referencing files absent from PR HEAD.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pr_number: Pull request number.

    Returns:
        Result dict with stale/active classification per comment.
    """
    try:
        threads = fetch_review_threads(owner, repo, pr_number)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Failed to fetch review threads for PR #{pr_number}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc

    try:
        pr_files = fetch_pr_files(owner, repo, pr_number)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Failed to fetch PR files for PR #{pr_number}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc

    comments: list[dict[str, Any]] = []
    for thread in threads:
        path = thread.get("path") or ""
        first_comment_nodes = thread.get("comments", {}).get("nodes", [])
        author = ""
        if first_comment_nodes and first_comment_nodes[0]:
            author_obj = first_comment_nodes[0].get("author") or {}
            author = author_obj.get("login", "")

        is_stale = bool(path) and path not in pr_files
        reason = "File not present at PR HEAD" if is_stale else ""

        comments.append({
            "ThreadId": thread.get("id", ""),
            "Path": path,
            "Line": thread.get("line"),
            "Author": author,
            "IsStale": is_stale,
            "Reason": reason,
        })

    stale_count = sum(1 for c in comments if c["IsStale"])
    active_count = len(comments) - stale_count

    print(
        f"PR #{pr_number}: {stale_count} stale / {active_count} active comments",
        file=sys.stderr,
    )

    return {
        "Success": True,
        "PullRequest": pr_number,
        "TotalComments": len(comments),
        "StaleComments": stale_count,
        "ActiveComments": active_count,
        "Comments": comments,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect PR review comments on files no longer at PR HEAD.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True,
        help="PR number",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    result = detect_stale_comments(owner, repo, args.pull_request)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
