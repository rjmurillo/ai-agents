#!/usr/bin/env python3
"""Verify commit references in resolved review threads are in the PR head."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = ""
    _here = os.path.abspath(os.path.dirname(__file__))
    _ancestor = _here
    while True:
        _candidate = os.path.join(_ancestor, "lib", "github_core")
        if os.path.isdir(_candidate):
            _lib_dir = os.path.dirname(_candidate)
            break
        _parent = os.path.dirname(_ancestor)
        if _parent == _ancestor:
            break
        _ancestor = _parent
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import assert_gh_authenticated, gh_graphql, resolve_repo_params

_MAX_THREAD_PAGES = 50
_SHA_RE = re.compile(r"\b([0-9a-f]{7,40})\b", re.IGNORECASE)

_THREADS_QUERY = """\
query($owner: String!, $repo: String!, $prNumber: Int!, $cursor: String) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
            headRefOid
            reviewThreads(first: 100, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                    path
                    line
                    comments(first: 100) {
                        totalCount
                        nodes {
                            id
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check resolved review-thread commit references.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Local git repository path used for ancestry checks.",
    )
    return parser


def _strip_fenced_code(body: str) -> str:
    kept: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            kept.append(line)
    return "\n".join(kept)


def extract_shas(body: str) -> list[str]:
    return [match.group(1).lower() for match in _SHA_RE.finditer(_strip_fenced_code(body))]


def fetch_review_threads(
    owner: str, repo: str, pull_request: int,
) -> tuple[str, list[dict[str, Any]], bool]:
    threads: list[dict[str, Any]] = []
    head_sha = ""
    cursor: str | None = None

    for _page in range(_MAX_THREAD_PAGES):
        variables: dict[str, Any] = {
            "owner": owner,
            "repo": repo,
            "prNumber": pull_request,
        }
        if cursor is not None:
            variables["cursor"] = cursor
        data = gh_graphql(_THREADS_QUERY, variables)
        pull_request_data = (data.get("repository") or {}).get("pullRequest")
        if not isinstance(pull_request_data, dict):
            raise RuntimeError(f"PR #{pull_request} not found")
        head_sha = str(pull_request_data.get("headRefOid") or head_sha)
        review_threads = pull_request_data.get("reviewThreads")
        if not isinstance(review_threads, dict):
            raise RuntimeError("reviewThreads missing from GraphQL response")
        page_nodes = review_threads.get("nodes") or []
        if not isinstance(page_nodes, list):
            raise RuntimeError("reviewThreads.nodes is not a list")
        threads.extend(t for t in page_nodes if isinstance(t, dict))

        page_info = review_threads.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            comments_complete = all(_thread_comments_complete(t) for t in threads)
            return head_sha, threads, comments_complete
        cursor = page_info.get("endCursor")
        if not cursor:
            return head_sha, threads, False
    return head_sha, threads, False


def _thread_comments_complete(thread: dict[str, Any]) -> bool:
    comments = thread.get("comments")
    if not isinstance(comments, dict):
        return False
    nodes = comments.get("nodes")
    if not isinstance(nodes, list):
        return False
    total = comments.get("totalCount")
    if not isinstance(total, int):
        return False
    return total == len(nodes)


def _latest_comment(thread: dict[str, Any]) -> dict[str, Any] | None:
    comments = thread.get("comments")
    if not isinstance(comments, dict):
        return None
    nodes = comments.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return None
    comment_nodes = [node for node in nodes if isinstance(node, dict)]
    if not comment_nodes:
        return None
    return max(comment_nodes, key=lambda c: str(c.get("createdAt") or ""))


def check_ancestor(sha: str, head_sha: str, repo_path: str) -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "-C", repo_path, "merge-base", "--is-ancestor", sha, head_sha],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 0:
        return True, "reachable"
    if result.returncode == 1:
        return False, "unreachable"
    return False, "invalid"


def build_report(
    owner: str,
    repo: str,
    pull_request: int,
    head_sha: str,
    threads: list[dict[str, Any]],
    fetched_pages_complete: bool,
    repo_path: str,
) -> dict[str, Any]:
    references: list[dict[str, Any]] = []
    resolved_threads = [t for t in threads if t.get("isResolved")]
    for thread in resolved_threads:
        comment = _latest_comment(thread)
        if comment is None:
            continue
        for sha in extract_shas(str(comment.get("body") or "")):
            reachable, status = check_ancestor(sha, head_sha, repo_path)
            author = comment.get("author")
            references.append(
                {
                    "thread_id": thread.get("id"),
                    "path": thread.get("path"),
                    "line": thread.get("line"),
                    "comment_id": comment.get("id"),
                    "comment_database_id": comment.get("databaseId"),
                    "comment_author": (
                        author.get("login") if isinstance(author, dict) else ""
                    ),
                    "comment_created_at": comment.get("createdAt"),
                    "sha": sha,
                    "reachable": reachable,
                    "status": status,
                }
            )

    unreachable_count = sum(1 for r in references if r["status"] == "unreachable")
    invalid_count = sum(1 for r in references if r["status"] == "invalid")
    return {
        "success": fetched_pages_complete,
        "pull_request": pull_request,
        "owner": owner,
        "repo": repo,
        "head_sha": head_sha,
        "thread_count": len(threads),
        "resolved_thread_count": len(resolved_threads),
        "sha_reference_count": len(references),
        "reachable_count": sum(1 for r in references if r["status"] == "reachable"),
        "unreachable_count": unreachable_count,
        "invalid_count": invalid_count,
        "fetched_pages_complete": fetched_pages_complete,
        "references": references,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.pull_request <= 0:
        print("Pull request number must be positive.", file=sys.stderr)
        return 2

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    try:
        head_sha, threads, fetched_pages_complete = fetch_review_threads(
            owner, repo, args.pull_request,
        )
    except RuntimeError as exc:
        print(f"Failed to fetch review threads: {exc}", file=sys.stderr)
        return 3

    report = build_report(
        owner,
        repo,
        args.pull_request,
        head_sha,
        threads,
        fetched_pages_complete,
        args.repo_path,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
