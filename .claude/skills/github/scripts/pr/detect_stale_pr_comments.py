#!/usr/bin/env python3
"""Detect PR review comments on files that no longer exist at PR HEAD.

When bot reviewers comment on multi-commit PRs, earlier comments may reference
files that were deleted or replaced in later commits.  This script identifies
those stale comments so they can be resolved or ignored.

Exit codes follow ADR-035:
    0 - Success
    2 - Configuration or usage error
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
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

_KNOWN_BOTS = frozenset({
    "copilot",
    "github-actions",
})
_BOT_SUFFIXES = ("[bot]", "-bot")

_REVIEW_THREADS_QUERY = """\
query($owner: String!, $name: String!, $prNumber: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100) {
                # Capped at 100; pagination not implemented (P2, rare edge case)
                nodes {
                    id
                    isOutdated
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

    Returns a list of thread dicts with id, path, line, and author.
    Limited to first 100 threads (no cursor pagination).

    Raises:
        RuntimeError: On GraphQL transport or response errors.
    """
    data = gh_graphql(
        _REVIEW_THREADS_QUERY,
        {"owner": owner, "name": repo, "prNumber": pr_number},
    )
    repo_data = data.get("repository") or {}
    pr_data = repo_data.get("pullRequest")
    if pr_data is None:
        print(
            f"PR not found in {owner}/{repo}",
            file=sys.stderr,
        )
        raise SystemExit(3)
    threads = (pr_data.get("reviewThreads") or {})
    nodes: list[dict[str, Any]] = threads.get("nodes") or []
    return nodes


def fetch_pr_files(owner: str, repo: str, pr_number: int) -> set[str]:
    """Fetch the set of file paths present in the PR at HEAD.

    Uses the GitHub REST API to get the file list.
    Excludes files with status 'removed' since they do not exist at HEAD.
    For renamed files, includes both the new filename and previous_filename
    to avoid false positives on review threads referencing the old path.
    """
    raw_files = gh_api_paginated(
        f"repos/{owner}/{repo}/pulls/{pr_number}/files"
    )
    result: set[str] = set()
    for f in raw_files:
        if f.get("status") == "removed":
            continue
        filename = f.get("filename", "")
        if filename:
            result.add(filename)
        previous = f.get("previous_filename", "")
        if previous:
            result.add(previous)
    return result


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _is_bot_author(login: str) -> bool:
    """Check if a login belongs to a bot reviewer.

    Uses a known-bots set for exact matches (e.g. "Copilot") plus
    suffix checks as a backstop for bots following naming conventions.
    """
    lower = login.lower()
    if lower in _KNOWN_BOTS:
        return True
    return any(lower.endswith(s) for s in _BOT_SUFFIXES)


def _classify_thread(
    thread: dict[str, Any], pr_files: set[str],
) -> dict[str, Any]:
    """Classify a single review thread as stale, outdated, or active."""
    path = thread.get("path") or ""
    is_outdated = thread.get("isOutdated", False)
    first_comment_nodes = thread.get("comments", {}).get("nodes", [])
    author = ""
    if first_comment_nodes and first_comment_nodes[0]:
        author_obj = first_comment_nodes[0].get("author") or {}
        author = author_obj.get("login", "")

    is_bot = _is_bot_author(author)
    file_missing = bool(path) and path not in pr_files

    if file_missing:
        reason = "File not present at PR HEAD"
    elif is_outdated:
        reason = "Thread marked outdated by GitHub (code changed since comment)"
    else:
        reason = ""

    return {
        "ThreadId": thread.get("id", ""),
        "Path": path,
        "Line": thread.get("line"),
        "Author": author,
        "IsBot": is_bot,
        "IsStale": file_missing,
        "IsOutdated": is_outdated,
        "Reason": reason,
    }


def _fetch_or_exit(
    fetch_fn: Callable[..., Any], owner: str, repo: str, pr_number: int, label: str,
) -> Any:
    """Call a fetch function, converting exceptions to ADR-035 exit 3."""
    try:
        return fetch_fn(owner, repo, pr_number)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Failed to fetch {label} for PR #{pr_number}: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc


def detect_stale_comments(
    owner: str, repo: str, pr_number: int, *, bot_only: bool = False,
) -> dict[str, Any]:
    """Detect review comments referencing files absent from PR HEAD.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pr_number: Pull request number.
        bot_only: If True, only classify bot-authored threads. Human
            threads are included in the output but never marked stale,
            preventing accidental bulk-resolution of human reviews.

    Returns a result dict with Owner, Repo, PullRequest, counts,
    and per-comment stale/outdated/active classification.
    """
    threads = _fetch_or_exit(fetch_review_threads, owner, repo, pr_number, "review threads")
    pr_files = _fetch_or_exit(fetch_pr_files, owner, repo, pr_number, "PR files")

    comments = [_classify_thread(t, pr_files) for t in threads]

    if bot_only:
        for c in comments:
            if not c["IsBot"]:
                c["IsStale"] = False
                c["IsOutdated"] = False
                c["Reason"] = "Skipped (human reviewer, --bot-only active)"

    stale_count = sum(1 for c in comments if c["IsStale"])
    outdated_count = sum(1 for c in comments if c["IsOutdated"] and not c["IsStale"])
    active_count = len(comments) - stale_count - outdated_count

    print(
        f"PR #{pr_number}: {stale_count} stale / {outdated_count} outdated / {active_count} active",
        file=sys.stderr,
    )

    return {
        "Success": True,
        "Owner": owner,
        "Repo": repo,
        "PullRequest": pr_number,
        "TotalComments": len(comments),
        "StaleComments": stale_count,
        "OutdatedComments": outdated_count,
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
    parser.add_argument(
        "--bot-only", action="store_true", default=False,
        help="Only classify bot-authored threads as stale. "
        "Human threads are reported but never marked stale.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    result = detect_stale_comments(
        owner, repo, args.pull_request, bot_only=args.bot_only,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
