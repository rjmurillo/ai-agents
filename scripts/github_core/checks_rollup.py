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

# The selection every caller must request inside `contexts { nodes { ... } }`.
# It is one constant because the field set is not a caller's choice: this module
# reads `completedAt`, `startedAt`, and `createdAt` for recency, and
# `checkSuite.workflowRun.workflow.name` for the grouping key, so a caller that
# queried fewer fields would collapse groups that must stay apart and rank runs
# it cannot order. Both invoke_pr_maintenance.py copies build their PR query
# around this constant.
CONTEXT_NODE_FIELDS = """\
... on CheckRun {
    name
    status
    conclusion
    startedAt
    completedAt
    checkSuite { workflowRun { workflow { name } } }
}
... on StatusContext {
    context
    state
    createdAt
}"""

_CONTEXTS_PAGE_QUERY = (
    """\
query($owner: String!, $repo: String!, $oid: GitObjectID!, $cursor: String!) {
    repository(owner: $owner, name: $repo) {
        object(oid: $oid) {
            ... on Commit {
                statusCheckRollup {
                    contexts(first: 100, after: $cursor) {
                        pageInfo { hasNextPage endCursor }
                        nodes {
"""
    + CONTEXT_NODE_FIELDS
    + """
                        }
                    }
                }
            }
        }
    }
}"""
)


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


def _context_workflow(node: dict[str, Any]) -> str:
    """Return the name of the workflow that owns this check run.

    A StatusContext carries no workflow and returns "". That is correct for
    it: a commit status is already one row per context name.
    """
    check_suite = node.get("checkSuite") or {}
    workflow_run = check_suite.get("workflowRun") or {}
    workflow = workflow_run.get("workflow") or {}
    return workflow.get("name") or ""


def _context_key(node: dict[str, Any]) -> tuple[str, str]:
    """Return the grouping key for a context node: (check name, workflow).

    The workflow half is load bearing. One check name can be recorded on a
    single head commit by several workflows: this repository has 9 workflows
    with a job named "Check Changed Paths" and 2 with "Aggregate Results".
    Those runs are concurrent siblings, not re-runs of each other, so the
    recency comparison between them is meaningless, and grouping on the name
    alone lets a passing job in one workflow discard a genuinely failing job
    in another. Measured on PR 4069: three FAILURE runs of "Check Changed
    Paths" completing at 01:26:07Z, 01:26:08Z, and 01:26:10Z were all
    discarded by a SUCCESS of the same name from the Python Tests workflow at
    01:26:11Z.

    The workflow name, not the check-suite id, is the discriminator that
    keeps re-run dedupe working: a re-run lands in a NEW check suite under
    the SAME workflow. Measured on PR 4040, oid 308e2094: the superseded
    "Validate PR" FAILURE sits in check suite 82979074639 and the later
    SUCCESS in 82982663213, both under workflow "PR Validation". Keying on
    the suite id would put them in different groups and lose the dedupe that
    Issue #3978 asked for.
    """
    return (_context_name(node), _context_workflow(node))


def _context_is_failing(node: dict[str, Any]) -> bool:
    """Return True if this single context node reports a failure."""
    return (
        node.get("conclusion") in _FAILING_CONCLUSIONS
        or node.get("state") in _FAILING_STATES
    )


def latest_contexts_by_run(
    nodes: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Keep only the most recent run for each (check name, workflow) pair.

    Ties on timestamp break on fetch order, so the last node returned by the
    API wins. Falsy nodes are dropped.
    """
    winners: dict[tuple[str, str], tuple[tuple[str, int], dict[str, Any]]] = {}
    for index, node in enumerate(nodes):
        if not node:
            continue
        recency = (_context_time(node), index)
        key = _context_key(node)
        current = winners.get(key)
        if current is None or recency > current[0]:
            winners[key] = (recency, node)
    return {key: entry[1] for key, entry in winners.items()}


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
        _context_is_failing(node) for node in latest_contexts_by_run(nodes).values()
    )
