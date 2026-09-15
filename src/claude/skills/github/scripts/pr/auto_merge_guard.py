#!/usr/bin/env python3
"""Guard GitHub auto-merge before resolving the final review thread."""

from __future__ import annotations

import os
import sys
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import gh_graphql

_THREAD_CONTEXT_QUERY = """\
query($threadId: ID!) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            id
            isResolved
            pullRequest {
                id
                number
                autoMergeRequest {
                    enabledAt
                    mergeMethod
                }
                repository {
                    name
                    owner {
                        login
                    }
                }
            }
        }
    }
}"""

_UNRESOLVED_THREADS_QUERY = """\
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
                }
            }
        }
    }
}"""

_DISABLE_MUTATION = """\
mutation($pullRequestId: ID!) {
    disablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId}) {
        pullRequest {
            id
            number
            autoMergeRequest {
                enabledAt
            }
        }
    }
}"""

_MAX_PAGES = 50


def _thread_context(thread_id: str) -> dict[str, Any] | None:
    data = gh_graphql(_THREAD_CONTEXT_QUERY, {"threadId": thread_id})
    node = data.get("node")
    return node if isinstance(node, dict) else None


def _fetch_unresolved_thread_ids(
    owner: str, repo: str, pr_number: int,
) -> tuple[list[str], bool]:
    unresolved: list[str] = []
    cursor: str | None = None

    for _ in range(_MAX_PAGES):
        variables: dict[str, Any] = {
            "owner": owner,
            "name": repo,
            "prNumber": pr_number,
        }
        if cursor:
            variables["cursor"] = cursor

        data = gh_graphql(_UNRESOLVED_THREADS_QUERY, variables)
        review_threads = (
            data.get("repository", {})
            .get("pullRequest", {})
            .get("reviewThreads")
        )
        if not isinstance(review_threads, dict):
            return unresolved, False

        for node in review_threads.get("nodes", []) or []:
            if isinstance(node, dict) and not node.get("isResolved", True):
                thread_id = node.get("id")
                if isinstance(thread_id, str):
                    unresolved.append(thread_id)

        page_info = review_threads.get("pageInfo", {}) or {}
        if not page_info.get("hasNextPage", False):
            return unresolved, True
        cursor = page_info.get("endCursor")
        if not cursor:
            return unresolved, False

    return unresolved, False


def _disable_auto_merge(pull_request_id: str) -> bool:
    data = gh_graphql(_DISABLE_MUTATION, {"pullRequestId": pull_request_id})
    auto_merge = (
        data.get("disablePullRequestAutoMerge", {})
        .get("pullRequest", {})
        .get("autoMergeRequest")
    )
    return auto_merge is None


def _pull_request_identity(pull_request: dict[str, Any]) -> tuple[str, str, int, str]:
    repository = pull_request.get("repository")
    owner_data = repository.get("owner") if isinstance(repository, dict) else None
    owner = owner_data.get("login") if isinstance(owner_data, dict) else None
    repo = repository.get("name") if isinstance(repository, dict) else None
    pr_number = pull_request.get("number")
    pr_id = pull_request.get("id")
    if not isinstance(owner, str) or not isinstance(repo, str):
        raise RuntimeError("thread pull request repository is incomplete")
    if not isinstance(pr_number, int) or not isinstance(pr_id, str):
        raise RuntimeError("thread pull request identity is incomplete")
    return owner, repo, pr_number, pr_id


def guard_auto_merge_before_final_thread_resolution(thread_id: str) -> dict[str, Any]:
    """Disable armed auto-merge if resolving ``thread_id`` would unblock merge."""
    context = _thread_context(thread_id)
    if context is None:
        return {"action": "NOOP", "reason": "thread_not_found"}
    if context.get("isResolved"):
        return {"action": "NOOP", "reason": "thread_already_resolved"}

    pull_request = context.get("pullRequest")
    if not isinstance(pull_request, dict):
        raise RuntimeError("thread has no pull request context")

    owner, repo, pr_number, pr_id = _pull_request_identity(pull_request)

    unresolved_ids, fetched_pages_complete = _fetch_unresolved_thread_ids(
        owner, repo, pr_number,
    )
    if not fetched_pages_complete:
        raise RuntimeError("could not prove unresolved review thread count")

    result: dict[str, Any] = {
        "pull_request": pr_number,
        "unresolved_count": len(unresolved_ids),
        "fetched_pages_complete": fetched_pages_complete,
        "auto_merge_was_armed": pull_request.get("autoMergeRequest") is not None,
    }

    if len(unresolved_ids) != 1:
        return {"action": "NOOP", "reason": "not_final_thread", **result}
    if unresolved_ids[0] != thread_id:
        raise RuntimeError("final unresolved thread changed before resolution")

    auto_merge = pull_request.get("autoMergeRequest")
    if not isinstance(auto_merge, dict):
        return {"action": "NOOP", "reason": "auto_merge_not_armed", **result}

    if not _disable_auto_merge(pr_id):
        raise RuntimeError("disablePullRequestAutoMerge did not clear autoMergeRequest")

    return {
        "action": "DISABLED",
        "reason": "final_thread_would_unblock_armed_auto_merge",
        "merge_method": auto_merge.get("mergeMethod"),
        "enabled_at": auto_merge.get("enabledAt"),
        **result,
    }
