"""Shared logic for grouping and evaluating GitHub status check rollups.

This module encodes the required-check semantics used by both get_pr_checks.py
and test_pr_merge_ready.py, preventing drift between the two scripts.

The key insight: a check name's required status is the OR of all isRequired
flags across all row types (CheckRun and StatusContext) for that name.
This is documented in issue #2325 and PR #1887 retrospective.
"""

from __future__ import annotations

from collections import defaultdict


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

_FAILURE_STATES = {"FAILURE", "ERROR"}


def context_name(context: dict) -> str:
    """Return the stable status-check name for CheckRun or StatusContext nodes."""
    name = context.get("name") or context.get("context")
    return "" if name is None else str(name)


def _context_timestamp(context: dict) -> str:
    """Return the best available timestamp for latest-run dedupe."""
    for key in ("completedAt", "startedAt", "createdAt"):
        value = context.get(key)
        if value:
            return str(value)
    return ""


def dedupe_contexts_by_latest(contexts: list[dict]) -> list[dict]:
    """Keep only the latest context for each check name.

    GitHub keeps older CheckRun rows on the same commit after a re-run. The PR
    maintenance scripts only need the current verdict, so timestamp wins within
    each name. Input order breaks ties, with the later row winning.
    """
    best_by_name: dict[str, tuple[tuple[str, int], dict]] = {}
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


def context_is_failing(context: dict) -> bool:
    """Return True when a rollup context carries a failing verdict."""
    conclusion = context.get("conclusion")
    state = context.get("state")
    return conclusion in _FAILURE_STATES or state in _FAILURE_STATES


def contexts_are_incomplete(contexts: dict) -> bool:
    """Return True when GraphQL reports more contexts than were fetched."""
    if contexts.get("__incomplete"):
        return True
    total = contexts.get("totalCount")
    nodes = contexts.get("nodes") or []
    return isinstance(total, int) and len(nodes) < total

