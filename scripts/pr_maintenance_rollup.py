"""Status-check rollup helpers for PR maintenance scripts."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

_FAILURE_STATES = {"FAILURE", "ERROR"}
_CONTEXTS_MAX_PAGES = 50

FetchContextPage = Callable[
    [str, str, str, str], tuple[list[dict[str, Any]], dict[str, Any]]
]

_STATUS_CONTEXT_PAGE_QUERY = """\
query($owner: String!, $name: String!, $oid: GitObjectID!, $cursor: String!) {
    repository(owner: $owner, name: $name) {
        object(oid: $oid) {
            ... on Commit {
                statusCheckRollup {
                    contexts(first: 100, after: $cursor) {
                        pageInfo {
                            hasNextPage
                            endCursor
                        }
                        nodes {
                            ... on CheckRun {
                                __typename
                                name
                                conclusion
                                status
                                startedAt
                                completedAt
                            }
                            ... on StatusContext {
                                __typename
                                context
                                state
                            }
                        }
                    }
                }
            }
        }
    }
}
"""


def fetch_status_context_page_with_graphql(
    owner: str,
    repo: str,
    oid: str,
    cursor: str,
    gh_graphql: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch one status-check context page through a GraphQL callable."""
    data = gh_graphql(
        _STATUS_CONTEXT_PAGE_QUERY,
        {"owner": owner, "name": repo, "oid": oid, "cursor": cursor},
    )
    commit = (data.get("repository") or {}).get("object") or {}
    rollup = commit.get("statusCheckRollup") or {}
    contexts = rollup.get("contexts") or {}
    return list(contexts.get("nodes") or []), contexts.get("pageInfo") or {}


def fetch_status_context_page_with_gh(
    owner: str,
    repo: str,
    oid: str,
    cursor: str,
    run_gh: Callable[..., Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch one status-check context page through a gh CLI wrapper."""
    result = run_gh(
        "api",
        "graphql",
        "-f",
        f"query={_STATUS_CONTEXT_PAGE_QUERY}",
        "-f",
        f"owner={owner}",
        "-f",
        f"name={repo}",
        "-f",
        f"oid={oid}",
        "-f",
        f"cursor={cursor}",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to paginate PR status checks: {result.stderr}")
    data = json.loads(result.stdout)
    commit = ((data.get("data") or {}).get("repository") or {}).get("object") or {}
    rollup = commit.get("statusCheckRollup") or {}
    contexts = rollup.get("contexts") or {}
    return list(contexts.get("nodes") or []), contexts.get("pageInfo") or {}


def context_name(context: dict[str, Any]) -> str:
    """Return the stable status-check name for CheckRun or StatusContext nodes."""
    name = context.get("name") or context.get("context")
    return "" if name is None else str(name)


def _context_timestamp(context: dict[str, Any]) -> str:
    """Return the best available timestamp for latest-run dedupe."""
    for key in ("completedAt", "startedAt", "createdAt"):
        value = context.get(key)
        if value:
            return str(value)
    return ""


def dedupe_contexts_by_latest(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the latest context for each check name."""
    best_by_name: dict[str, tuple[tuple[str, int], dict[str, Any]]] = {}
    order: list[str] = []
    for index, context in enumerate(contexts):
        name = context_name(context)
        key = (_context_timestamp(context), index)
        current = best_by_name.get(name)
        if current is None:
            best_by_name[name] = (key, context)
            order.append(name)
            continue
        if key > current[0]:
            best_by_name[name] = (key, context)
    return [best_by_name[name][1] for name in order]


def context_is_failing(context: dict[str, Any]) -> bool:
    """Return True when a rollup context carries a failing verdict."""
    conclusion = context.get("conclusion")
    state = context.get("state")
    return conclusion in _FAILURE_STATES or state in _FAILURE_STATES


def contexts_are_incomplete(contexts: dict[str, Any]) -> bool:
    """Return True when GraphQL reports more contexts than were fetched."""
    if contexts.get("__incomplete"):
        return True
    total = contexts.get("totalCount")
    nodes = contexts.get("nodes") or []
    return isinstance(total, int) and len(nodes) < total


def rollup_has_failing_checks(
    rollup: dict[str, Any],
    pr_number: object = "?",
) -> bool:
    """Return True when a rollup fails or is incomplete."""
    if rollup.get("state", "") in _FAILURE_STATES:
        return True

    contexts = rollup.get("contexts") or {}
    if contexts_are_incomplete(contexts):
        logging.error("PR #%s has incomplete statusCheckRollup contexts", pr_number)
        return True

    return any(
        context_is_failing(ctx)
        for ctx in dedupe_contexts_by_latest(contexts.get("nodes", []) or [])
    )


def complete_status_check_rollups(
    owner: str,
    repo: str,
    prs: list[dict[str, Any]],
    fetch_context_page: FetchContextPage,
) -> None:
    """Fetch remaining status-check context pages for every PR node."""
    for pr in prs:
        commits = pr.get("commits") or {}
        commit_nodes = commits.get("nodes") or []
        if not commit_nodes:
            continue
        commit = commit_nodes[0].get("commit") or {}
        _complete_commit_rollup(owner, repo, commit, fetch_context_page)


def _complete_commit_rollup(
    owner: str,
    repo: str,
    commit: dict[str, Any],
    fetch_context_page: FetchContextPage,
) -> None:
    oid = commit.get("oid")
    rollup = commit.get("statusCheckRollup") or {}
    contexts = rollup.get("contexts") or {}
    page_info = contexts.get("pageInfo") or {}
    nodes = list(contexts.get("nodes") or [])
    complete = True
    cursor = page_info.get("endCursor")
    for _ in range(_CONTEXTS_MAX_PAGES):
        if not page_info.get("hasNextPage"):
            break
        if not oid or not cursor:
            complete = False
            break
        try:
            page_nodes, page_info = fetch_context_page(owner, repo, oid, cursor)
        except (RuntimeError, ValueError, KeyError):
            complete = False
            break
        nodes.extend(page_nodes)
        cursor = page_info.get("endCursor")
    else:
        complete = False

    contexts["nodes"] = nodes
    total = contexts.get("totalCount")
    if isinstance(total, int) and len(nodes) < total:
        complete = False
    contexts["__incomplete"] = not complete
