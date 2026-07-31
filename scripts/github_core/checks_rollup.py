"""Shared logic for grouping and evaluating GitHub status check rollups.

This module encodes the required-check semantics used by both get_pr_checks.py
and test_pr_merge_ready.py, preventing drift between the two scripts.

The key insight: a check name's required status is the OR of all isRequired
flags across all row types (CheckRun and StatusContext) for that name.
This is documented in issue #2325 and PR #1887 retrospective.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from scripts.github_core.api import gh_graphql

logger = logging.getLogger(__name__)


def group_checks_by_name(
    checks: list[dict],
) -> tuple[dict[str, dict], dict[str, bool], dict[str, list[str]]]:
    """Group checks by name, tracking required status and type.

    Returns (checks_by_name, is_required_by_name, check_types_by_name) where:
    - checks_by_name: maps check name to the normalized check dict
    - is_required_by_name: maps check name to OR of all isRequired values
    - check_types_by_name: maps check name to list of types present (for dedupe)

    The isRequired flag ORs across rows: if ANY row for a name has
    isRequired=true, the name is treated as required. This matches the
    test_pr_merge_ready.py _group_contexts_by_name logic.
    """
    checks_by_name: dict[str, dict] = {}
    is_required_by_name: dict[str, bool] = {}
    check_types_by_name: dict[str, list[str]] = defaultdict(list)

    for check in checks:
        name = check.get("Name", "")
        typename = check.get("Type", "")

        # Track type for dedupe ordering (CheckRun preferred over StatusContext).
        if typename and typename not in check_types_by_name[name]:
            check_types_by_name[name].append(typename)

        # OR the required flag: if any row for this name is required, the name
        # is treated as required.
        is_required_by_name[name] = (
            is_required_by_name.get(name, False) or bool(check.get("IsRequired"))
        )

        # Keep the first check of each name (caller has already deduplicated by
        # passing the winner from dedupe_checks).
        if name not in checks_by_name:
            checks_by_name[name] = check

    return checks_by_name, is_required_by_name, check_types_by_name


def extract_required_check_lists(
    checks: list[dict],
    is_required_by_name: dict[str, bool],
) -> tuple[list[str], list[str]]:
    """Extract pending and failed required check names.

    Returns (pending_required_names, failed_required_names) for structured
    output in JSON so downstream agents can distinguish pending vs. failed
    required checks.
    """
    pending_required = []
    failed_required = []

    for check in checks:
        name = check.get("Name", "")
        is_required = is_required_by_name.get(name, False)

        if not is_required:
            continue

        if check.get("IsFailing"):
            failed_required.append(name)
        # A check whose dedupe winner is passing (SUCCESS, NEUTRAL, or SKIPPED)
        # is not a pending required check, even when dedupe_checks ORed
        # IsPending=true onto the winner from a stale sibling row. The IsPending
        # OR is retained on the row for wait polling, but PendingRequiredChecks
        # must classify a completed-passing required check consistently with
        # test_pr_merge_ready.py, which treats it as non-blocking. Refs issue #2614:
        # a SKIPPED required check with a PENDING sibling was reported as pending.
        if check.get("IsPending") and not check.get("IsPassing"):
            pending_required.append(name)

    return pending_required, failed_required


# ---------------------------------------------------------------------------
# Raw rollup evaluation (superseded-run dedupe + context pagination)
# ---------------------------------------------------------------------------
#
# `statusCheckRollup` is per head commit and keeps EVERY check run recorded for
# a name, including runs a later re-run superseded. `rollup.state` aggregates
# all of them, so a check that failed and then passed on a re-run without a new
# commit leaves `state` at FAILURE forever. Deciding from the latest run per
# name instead of from `state` is what clears it. Refs Issue #3978.
#
# Ordering is by RECENCY, not by the verdict precedence in `dedupe_checks` in
# `skills/github/scripts/pr/get_pr_checks.py` (path relative to the plugin
# root), which ranks passing above failing per Issue #2208. Precedence would
# classify "superseded SUCCESS, then a later FAILURE" as passing, which is the
# exact inverse case this dispatcher must still wake on.
#
# The failing-conclusion set is copied verbatim from `_FAILING_CONCLUSIONS` in
# that same file:
#
#     _FAILING_CONCLUSIONS = {
#         "FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED",
#         "STALE", "STARTUP_FAILURE",
#     }
#
# It must stay that wide here: once `rollup.state` is no longer the decider, a
# TIMED_OUT or CANCELLED run that `state` used to catch would otherwise go
# unreported, which is a fail-open.

_FAILING_CONCLUSIONS = frozenset(
    {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STALE", "STARTUP_FAILURE"}
)
_FAILING_STATES = frozenset({"FAILURE", "ERROR"})
_CONTEXTS_MAX_PAGES = 50

_CONTEXTS_PAGE_QUERY = """\
query($owner: String!, $repo: String!, $oid: GitObjectID!, $cursor: String!) {
    repository(owner: $owner, name: $repo) {
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
                                name
                                status
                                conclusion
                                startedAt
                                completedAt
                            }
                            ... on StatusContext {
                                context
                                state
                                createdAt
                            }
                        }
                    }
                }
            }
        }
    }
}"""


def _context_name(node: dict[str, Any]) -> str:
    """Return the check name for a CheckRun or StatusContext node."""
    return node.get("name") or node.get("context") or ""


def _context_time(node: dict[str, Any]) -> str:
    """Return the recency key for a context node.

    GitHub timestamps are ISO 8601 UTC, so lexical order is chronological.
    An absent timestamp sorts first, which keeps a node that carries one as
    the winner over a node that does not.
    """
    return node.get("completedAt") or node.get("startedAt") or node.get("createdAt") or ""


def _context_is_failing(node: dict[str, Any]) -> bool:
    """Return True if this single context node reports a failure."""
    return (
        node.get("conclusion") in _FAILING_CONCLUSIONS
        or node.get("state") in _FAILING_STATES
    )


def latest_contexts_by_name(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep only the most recent run for each check name.

    Ties on timestamp break on fetch order, so the last node returned by the
    API wins. Falsy nodes are dropped.
    """
    winners: dict[str, tuple[tuple[str, int], dict[str, Any]]] = {}
    for index, node in enumerate(nodes):
        if not node:
            continue
        key = (_context_time(node), index)
        name = _context_name(node)
        current = winners.get(name)
        if current is None or key > current[0]:
            winners[name] = (key, node)
    return {name: entry[1] for name, entry in winners.items()}


def _page_contexts(data: dict[str, Any]) -> dict[str, Any]:
    """Extract the `contexts` connection from one page response."""
    repository = data.get("repository") or {}
    commit = repository.get("object") or {}
    rollup = commit.get("statusCheckRollup") or {}
    return rollup.get("contexts") or {}


def _fetch_remaining_contexts(
    owner: str,
    repo: str,
    oid: str,
    cursor: str,
    graphql: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Page the rest of the contexts connection.

    Returns (nodes, complete). ``complete`` is False when a page call failed
    or the cursor chain broke, so the caller can fall back rather than decide
    from a partial set.
    """
    if not cursor:
        return [], False

    extras: list[dict[str, Any]] = []
    for _ in range(_CONTEXTS_MAX_PAGES):
        try:
            data = graphql(
                _CONTEXTS_PAGE_QUERY,
                {"owner": owner, "repo": repo, "oid": oid, "cursor": cursor},
            )
        except RuntimeError:
            logger.exception(
                "Failed to page status-check contexts for %s/%s at %s", owner, repo, oid
            )
            return extras, False
        contexts = _page_contexts(data)
        extras.extend(contexts.get("nodes") or [])
        page_info = contexts.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return extras, True
        cursor = page_info.get("endCursor") or ""
        if not cursor:
            return extras, False

    return extras, False


def _collect_contexts(
    contexts: dict[str, Any],
    *,
    owner: str,
    repo: str,
    oid: str,
    graphql: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Return (all context nodes, complete) for one rollup."""
    nodes = [node for node in (contexts.get("nodes") or []) if node]
    page_info = contexts.get("pageInfo") or {}
    complete = True

    if page_info.get("hasNextPage"):
        if not (owner and repo and oid):
            return nodes, False
        extras, complete = _fetch_remaining_contexts(
            owner, repo, oid, page_info.get("endCursor") or "", graphql
        )
        nodes.extend(node for node in extras if node)

    total = contexts.get("totalCount")
    if complete and isinstance(total, int) and len(nodes) < total:
        complete = False
    return nodes, complete


def rollup_has_failing_checks(
    rollup: dict[str, Any] | None,
    *,
    owner: str = "",
    repo: str = "",
    oid: str = "",
    pr_number: int | str = "?",
    graphql: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
) -> bool:
    """Return True when the latest run of any check on this commit failed.

    Superseded runs are discarded, so a FAILURE followed by a SUCCESS for the
    same name reads as passing and the inverse reads as failing.

    When the context set cannot be completed (pagination failed, no commit oid
    to page with, or fewer nodes fetched than ``totalCount``), this falls back
    to ``rollup.state``, which is the pre-Issue-#3978 behavior. That keeps a
    truncated read fail-closed instead of silently deciding from a partial set.
    """
    if not rollup:
        return False

    nodes, complete = _collect_contexts(
        rollup.get("contexts") or {},
        owner=owner,
        repo=repo,
        oid=oid,
        graphql=graphql or gh_graphql,
    )
    if not complete:
        logger.error(
            "PR #%s: incomplete status-check contexts (%d fetched of %s); "
            "falling back to rollup state %s",
            pr_number,
            len(nodes),
            (rollup.get("contexts") or {}).get("totalCount", "unknown"),
            rollup.get("state"),
        )
        return rollup.get("state") in _FAILING_STATES

    return any(
        _context_is_failing(node) for node in latest_contexts_by_name(nodes).values()
    )
