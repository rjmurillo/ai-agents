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
                state
                headRefOid
                baseRefName
                baseRefOid
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
    owner: str,
    repo: str,
    pr_number: int,
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
        review_threads = data.get("repository", {}).get("pullRequest", {}).get("reviewThreads")
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
    payload = data.get("disablePullRequestAutoMerge")
    pull_request = payload.get("pullRequest") if isinstance(payload, dict) else None
    if not isinstance(pull_request, dict):
        raise RuntimeError("disablePullRequestAutoMerge returned no pullRequest payload")
    return pull_request.get("autoMergeRequest") is None


def identity_mismatches(
    pull_request: dict[str, Any],
    expected: dict[str, str] | None,
) -> list[str]:
    """Name each live PR identity field that differs from the caller's expectation.

    ``expected`` carries the head SHA, base ref, and base SHA captured by the
    readiness cycle. This helper reports no mismatch for an empty expectation;
    the guard entry point refuses an empty binding before it gets here. When
    any is supplied the PR must also still be OPEN: a merged PR keeps its head
    SHA, so a SHA match alone cannot prove the session still owns a live branch.
    """
    if not expected:
        return []
    comparisons = (
        ("head SHA", expected.get("head_sha"), pull_request.get("headRefOid")),
        ("base ref", expected.get("base_ref"), pull_request.get("baseRefName")),
        ("base SHA", expected.get("base_sha"), pull_request.get("baseRefOid")),
    )
    mismatches = [label for label, want, actual in comparisons if want and want != actual]
    if pull_request.get("state") != "OPEN":
        mismatches.insert(0, "state")
    return mismatches


def _has_identity_binding(expected: dict[str, str] | None) -> bool:
    """True when the caller bound at least one of head SHA, base ref, base SHA.

    Any one field is accepted so a caller that captured only the base ref still
    gets the OPEN-state check ``identity_mismatches`` adds for every binding,
    which refuses a merged or closed PR. Only a SHA binding detects a moved
    head, which is why the skill docs and pr-autofix pass ``--expected-head-sha``.
    """
    if not expected:
        return False
    return any(expected.get(key) for key in ("head_sha", "base_ref", "base_sha"))


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


def guard_auto_merge_before_final_thread_resolution(
    thread_id: str,
    expected_identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Disable armed auto-merge if resolving ``thread_id`` would unblock merge.

    ``expected_identity`` must bind at least one of ``head_sha``, ``base_ref``,
    or ``base_sha``; an empty binding raises ``RuntimeError`` before any call.
    The live PR must still match it before anything is counted or disabled. A
    mismatch raises ``RuntimeError`` with no mutation, so a stale session cannot
    disarm auto-merge on a PR that moved.
    """
    if not _has_identity_binding(expected_identity):
        raise RuntimeError(
            "expected identity needs at least one of head_sha, base_ref, base_sha; "
            "auto-merge left untouched"
        )
    context = _thread_context(thread_id)
    if context is None:
        return {"action": "NOOP", "reason": "thread_not_found"}
    if context.get("isResolved"):
        return {"action": "NOOP", "reason": "thread_already_resolved"}

    pull_request = context.get("pullRequest")
    if not isinstance(pull_request, dict):
        raise RuntimeError("thread has no pull request context")

    mismatches = identity_mismatches(pull_request, expected_identity)
    if mismatches:
        raise RuntimeError(
            f"pull request identity changed ({', '.join(mismatches)}); auto-merge left untouched"
        )

    owner, repo, pr_number, pr_id = _pull_request_identity(pull_request)

    unresolved_ids, fetched_pages_complete = _fetch_unresolved_thread_ids(
        owner,
        repo,
        pr_number,
    )
    if not fetched_pages_complete:
        raise RuntimeError("could not prove unresolved review thread count")

    result: dict[str, Any] = {
        "pull_request": pr_number,
        "unresolved_count": len(unresolved_ids),
        "fetched_pages_complete": fetched_pages_complete,
        "auto_merge_was_armed": pull_request.get("autoMergeRequest") is not None,
    }

    if thread_id not in unresolved_ids:
        raise RuntimeError("final unresolved thread changed before resolution")
    if len(unresolved_ids) != 1:
        return {"action": "NOOP", "reason": "not_final_thread", **result}

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
