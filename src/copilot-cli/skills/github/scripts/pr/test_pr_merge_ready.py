#!/usr/bin/env python3
"""Check if a PR is ready to merge.

Performs comprehensive merge readiness check:
- Verifies all review threads are resolved
- Checks CI status (required checks passing by default)
- Validates PR state (open, not draft)
- Checks for merge conflicts

By default, only REQUIRED checks block merge. Non-required failing checks
are reported but do not affect CanMerge unless --include-non-required is set.

Multiple rows for the same check name (supersession: a CANCELLED or FAILURE
run plus a later SUCCESS run) are deduplicated by name. The verdict per
name is OK if any conclusion is SUCCESS / NEUTRAL / SKIPPED (superseding
prior failures from re-runs); FAIL if any conclusion is a real failure and
no passing row exists; PENDING if any status is IN_PROGRESS / PENDING.
A name whose only conclusion is CANCELLED carries no opinion and does not
block. The PR #1887 retrospective records four false-FAIL reports caused
by counting CANCELLED debounce rows as failed required checks.

The output JSON includes a ``fetched_pages_complete`` field that is true
only when both ``reviewThreads`` and ``statusCheckRollup.contexts`` were
returned in their entirety by the inline GraphQL query. The /pr-review
completion gate's pass_when expression requires this flag to be true; a
partial fetch that happens to find no failing checks is not evidence
that no failing checks exist. This addresses the pagination-cliff
masking failure documented in retrospective
2026-05-05-pr-1887-iteration-paradox.md.

Exit codes follow ADR-035:
    0 - PR is ready to merge
    1 - PR is not ready to merge
    2 - PR not found
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

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
    count_unresolved_threads,
    error_and_exit,
    get_unresolved_review_threads,
    gh_graphql,
    resolve_repo_params,
    safe_log_str,
)

# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------

# Cap on context pagination loops. A PR with more than 5000 status
# contexts (50 pages * 100 per page) is far past anything operational;
# refuse to spin forever and surface the truncation as
# fetched_pages_complete=False.
_CONTEXTS_MAX_PAGES = 50


# Follow-up query used when the merge-ready inline page truncates the
# contexts list. Re-fetches the same commit by SHA and pages contexts
# from the cursor returned by the previous call.
_CONTEXTS_PAGE_QUERY = """\
query($owner: String!, $repo: String!, $oid: GitObjectID!, $number: Int!, $cursor: String!) {
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
                                __typename
                                name
                                status
                                conclusion
                                isRequired(pullRequestNumber: $number)
                            }
                            ... on StatusContext {
                                __typename
                                context
                                state
                                isRequired(pullRequestNumber: $number)
                            }
                        }
                    }
                }
            }
        }
    }
}"""


_MERGE_READY_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            state
            isDraft
            mergeable
            mergeStateStatus
            reviewThreads(first: 100) {
                totalCount
                nodes {
                    id
                    isResolved
                }
            }
            commits(last: 1) {
                nodes {
                    commit {
                        oid
                        statusCheckRollup {
                            state
                            contexts(first: 100) {
                                totalCount
                                pageInfo {
                                    hasNextPage
                                    endCursor
                                }
                                nodes {
                                    ... on CheckRun {
                                        __typename
                                        name
                                        status
                                        conclusion
                                        isRequired(pullRequestNumber: $number)
                                    }
                                    ... on StatusContext {
                                        __typename
                                        context
                                        state
                                        isRequired(pullRequestNumber: $number)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}"""


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

# Conclusions that count as success for a CheckRun. Aligned with the existing
# script behavior: SUCCESS, NEUTRAL, and SKIPPED have always been treated as
# non-blocking by this code.
_PASSING_CONCLUSIONS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})

# CANCELLED is NOT a real failure: it indicates a workflow run that was
# superseded (typically by a debounce mechanism that cancels the older run
# in favor of a fresh one). The PR #1887 retrospective records four false-
# FAIL reports caused by counting CANCELLED debounce rows as failed required
# checks; the dedupe logic in _classify_check_contexts treats a CANCELLED
# row as carrying no opinion when paired with a SUCCESS row of the same name.
_NO_OPINION_CONCLUSIONS = frozenset({"CANCELLED"})

# StatusContext states that count as success.
_PASSING_STATUS_STATES = frozenset({"SUCCESS", "EXPECTED"})


def _check_run_verdict(rows: list[dict]) -> str:
    """Reduce multiple CheckRun rows for one name to a single verdict.

    Verdict precedence:
      1. OK    - any row has a passing conclusion (SUCCESS/NEUTRAL/SKIPPED).
                 A re-run SUCCESS supersedes a stale FAILURE from an earlier
                 run, closing the same false-FAIL class as the CANCELLED fix.
      2. FAIL  - any row has a real failure conclusion (not in the passing
                 or no-opinion sets, e.g. FAILURE, TIMED_OUT, ACTION_REQUIRED).
      3. PENDING - any row has status != COMPLETED (and no passing row).
      4. SKIP  - all rows are CANCELLED (no real opinion); not blocking.

    Aligns with the brief in the PR #1887 retrospective: "OK if any SUCCESS
    exists." A passing conclusion from a re-run supersedes a prior failure.
    """
    has_failure = False
    has_pending = False
    has_passing = False

    for row in rows:
        status = row.get("status", "")
        conclusion = row.get("conclusion", "")

        if status != "COMPLETED":
            has_pending = True
            continue
        if conclusion in _PASSING_CONCLUSIONS:
            has_passing = True
        elif conclusion in _NO_OPINION_CONCLUSIONS:
            # CANCELLED row: contributes nothing (no opinion).
            continue
        else:
            has_failure = True

    if has_passing:
        return "OK"
    if has_failure:
        return "FAIL"
    if has_pending:
        return "PENDING"
    return "SKIP"


def _status_context_verdict(rows: list[dict]) -> str:
    """Reduce multiple StatusContext rows for one name to a single verdict.

    StatusContext does not surface CANCELLED; the typical states are SUCCESS,
    EXPECTED, PENDING, FAILURE, ERROR. We apply the same precedence as the
    CheckRun verdict so callers can treat the two row types uniformly:
    OK > FAIL > PENDING > SKIP.
    """
    has_failure = False
    has_pending = False
    has_passing = False

    for row in rows:
        state = row.get("state", "")
        if state == "PENDING":
            has_pending = True
        elif state in _PASSING_STATUS_STATES:
            has_passing = True
        else:
            has_failure = True

    if has_passing:
        return "OK"
    if has_failure:
        return "FAIL"
    if has_pending:
        return "PENDING"
    return "SKIP"


def _group_contexts_by_name(
    contexts: list[dict],
) -> tuple[dict[str, list[dict]], dict[str, list[dict]], dict[str, bool]]:
    """Group rollup contexts by check name. Returns ``(check_runs,
    status_contexts, is_required_by_name)``.

    The is_required flag ORs across rows: if any row carries isRequired=true,
    the name is treated as required (the rollup may publish both a CheckRun
    and a StatusContext for the same logical check; required may live on one).
    """
    grouped_check_runs: dict[str, list[dict]] = defaultdict(list)
    grouped_status_contexts: dict[str, list[dict]] = defaultdict(list)
    is_required_by_name: dict[str, bool] = {}

    for ctx in contexts:
        typename = ctx.get("__typename")
        if typename == "CheckRun":
            name = ctx.get("name", "unknown")
            grouped_check_runs[name].append(ctx)
        elif typename == "StatusContext":
            name = ctx.get("context", "unknown")
            grouped_status_contexts[name].append(ctx)
        else:
            continue
        is_required_by_name[name] = (
            is_required_by_name.get(name, False)
            or bool(ctx.get("isRequired", False))
        )
    return grouped_check_runs, grouped_status_contexts, is_required_by_name


def _route_check_run_groups(
    grouped: dict[str, list[dict]],
    is_required_by_name: dict[str, bool],
    *,
    failed_required: list[str], pending_required: list[str],
    failed_non_required: list[str], pending_non_required: list[str],
    skipped_names: list[str],
) -> None:
    """Verdict + route + dedupe-log for each CheckRun group."""
    for name, rows in grouped.items():
        verdict = _check_run_verdict(rows)
        is_required = is_required_by_name.get(name, False)
        if len(rows) > 1:
            logger.debug(
                "op=check_run_dedupe name=%s rows=%s verdict=%s required=%s",
                name,
                [(r.get("status"), r.get("conclusion")) for r in rows],
                verdict, is_required,
            )
        _route_verdict(name, verdict, is_required,
                       failed_required, pending_required,
                       failed_non_required, pending_non_required,
                       skipped_names=skipped_names)


def _route_status_context_groups(
    grouped: dict[str, list[dict]],
    seen_check_run_names: set[str],
    is_required_by_name: dict[str, bool],
    *,
    failed_required: list[str], pending_required: list[str],
    failed_non_required: list[str], pending_non_required: list[str],
    skipped_names: list[str],
) -> None:
    """Verdict + route for StatusContext groups; skip duplicates of
    CheckRun names (rollup may publish both for the same logical check).
    """
    for name, rows in grouped.items():
        if name in seen_check_run_names:
            logger.debug(
                "op=status_context_skipped reason=dup_of_check_run "
                "name=%s rows=%d",
                name, len(rows),
            )
            continue
        verdict = _status_context_verdict(rows)
        is_required = is_required_by_name.get(name, False)
        if len(rows) > 1:
            logger.debug(
                "op=status_context_dedupe name=%s rows=%s verdict=%s required=%s",
                name,
                [r.get("state") for r in rows],
                verdict, is_required,
            )
        _route_verdict(name, verdict, is_required,
                       failed_required, pending_required,
                       failed_non_required, pending_non_required,
                       skipped_names=skipped_names)


def _classify_check_contexts(
    contexts: list[dict],
    *,
    failed_required: list[str],
    pending_required: list[str],
    failed_non_required: list[str],
    pending_non_required: list[str],
    skipped_names: list[str],
) -> None:
    """Group rollup contexts by name; route each group's verdict to a bucket.

    Multiple rows under the same name (debounce supersession) collapse via
    _check_run_verdict / _status_context_verdict before routing. A verdict
    of OK appends to nothing (caller computes passed_checks from the
    surviving names minus blocked minus skipped). A verdict of SKIP
    (CANCELLED-only, no opinion) appends to ``skipped_names`` so the
    passed-checks count can subtract it out — without that subtraction,
    a debounce-cancelled rollup would be counted as passed.

    Closes the false-FAIL class on CANCELLED+SUCCESS dedupe AND the
    false-PASS class on CANCELLED-only debounce groups.
    """
    grouped_check_runs, grouped_status_contexts, is_required_by_name = (
        _group_contexts_by_name(contexts)
    )
    _route_check_run_groups(
        grouped_check_runs, is_required_by_name,
        failed_required=failed_required, pending_required=pending_required,
        failed_non_required=failed_non_required,
        pending_non_required=pending_non_required,
        skipped_names=skipped_names,
    )
    _route_status_context_groups(
        grouped_status_contexts,
        seen_check_run_names=set(grouped_check_runs.keys()),
        is_required_by_name=is_required_by_name,
        failed_required=failed_required, pending_required=pending_required,
        failed_non_required=failed_non_required,
        pending_non_required=pending_non_required,
        skipped_names=skipped_names,
    )


def _route_verdict(
    name: str,
    verdict: str,
    is_required: bool,
    failed_required: list[str],
    pending_required: list[str],
    failed_non_required: list[str],
    pending_non_required: list[str],
    skipped_names: list[str] | None = None,
) -> None:
    """Append name to the appropriate bucket given its verdict.

    SKIP-verdict names (CANCELLED-only, no opinion) are tracked separately
    in ``skipped_names`` when provided. They neither block nor count as
    passed; the caller subtracts them from the passed-checks total.
    """
    if verdict == "FAIL":
        (failed_required if is_required else failed_non_required).append(name)
    elif verdict == "PENDING":
        (pending_required if is_required else pending_non_required).append(name)
    elif verdict == "SKIP" and skipped_names is not None:
        skipped_names.append(name)


def _count_passed_checks(
    contexts: list[dict],
    blocked: list[str],
    skipped: list[str] | None = None,
) -> int:
    """Count distinct check names that are not blocked AND not skipped.

    Uses the post-dedupe blocked list and (optionally) the skipped list
    to compute "everything else passed". A SKIP-verdict name (CANCELLED-
    only group) is no-opinion, NOT passed; without subtracting skipped,
    the count overstates by the number of debounce-cancelled rollups.
    """
    distinct_names: set[str] = set()
    for ctx in contexts:
        typename = ctx.get("__typename")
        if typename == "CheckRun":
            distinct_names.add(ctx.get("name", "unknown"))
        elif typename == "StatusContext":
            distinct_names.add(ctx.get("context", "unknown"))
    excluded = set(blocked)
    if skipped:
        excluded.update(skipped)
    return len(distinct_names - excluded)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _fetch_pr_data(owner: str, repo: str, pr_number: int, op_start: float) -> dict:
    """Run the merge-ready GraphQL query. Exits on auth/transport/missing PR.

    Emits a structured `op=merge_ready_failed reason=... duration_ms=...`
    log line on every error path so an operator at 3am can grep the failure
    surface without reading source.
    """
    try:
        data = gh_graphql(
            _MERGE_READY_QUERY,
            {"owner": owner, "repo": repo, "number": pr_number},
        )
    except RuntimeError as exc:
        msg = str(exc)
        duration_ms = int((time.monotonic() - op_start) * 1000)
        if "Could not resolve" in msg:
            logger.warning(
                "op=merge_ready_failed pr=%d owner=%s repo=%s "
                "reason=pr_not_found duration_ms=%d",
                pr_number, owner, repo, duration_ms,
            )
            error_and_exit(f"PR #{pr_number} not found in {owner}/{repo}", 2)
        logger.warning(
            "op=merge_ready_failed pr=%d owner=%s repo=%s "
            "reason=graphql_error duration_ms=%d error=%s",
            pr_number, owner, repo, duration_ms, safe_log_str(msg),
        )
        error_and_exit(f"Failed to query PR status: {msg}", 3)

    pr = data.get("repository", {}).get("pullRequest")
    if pr is None:
        duration_ms = int((time.monotonic() - op_start) * 1000)
        # Use reason=pr_not_found to align with the cross-script taxonomy
        # in api.py::get_unresolved_review_threads and get_pr_review_threads.
        # Operators grepping `reason=pr_not_found` find every script that
        # observed this condition, regardless of which one logged it.
        logger.warning(
            "op=merge_ready_failed pr=%d owner=%s repo=%s "
            "reason=pr_not_found duration_ms=%d",
            pr_number, owner, repo, duration_ms,
        )
        error_and_exit(f"PR #{pr_number} not found", 2)
    return pr


def _merge_state_status(pr: dict) -> str:
    value = pr.get("mergeStateStatus")
    return "" if value is None else str(value)


def _evaluate_pr_state(pr: dict, reasons: list[str]) -> str:
    """Append draft/state/merge-conflict reasons; return mergeable string.

    Also gates on ``mergeStateStatus == BEHIND`` (issue #2157): a branch
    behind its base cannot land, and this repo does not auto-update it on
    auto-merge (issue #2048 concrete failure), so it must block. ``DRAFT``,
    ``DIRTY``, and ``UNKNOWN`` are already covered by the ``isDraft`` and
    ``mergeable`` checks.

    ``mergeStateStatus == BLOCKED`` blocks (issue #2326). A BLOCKED state
    means GitHub's branch protection still refuses the merge: a missing
    required review decision, an unmet branch-protection rule, or another
    protection gate. The previous behavior treated BLOCKED as a pass on the
    theory that "awaiting required review" is when enabling auto-merge is
    correct; that produced a false ready signal for PRs that branch protection
    actually refused (observed on PR #2323) and conflicted with this repo's
    own four-condition merge gate (``.claude/commands/pr-autofix.md``,
    ``.claude/commands/pr-review-config.yaml``), which both require
    ``mergeStateStatus in ('CLEAN', 'UNSTABLE')``.
    """
    if pr["state"] != "OPEN":
        reasons.append(f"PR is {pr['state'].lower()}, not open")
    if pr.get("isDraft"):
        reasons.append("PR is in draft state")
    mergeable = pr.get("mergeable", "")
    if mergeable == "CONFLICTING":
        reasons.append("PR has merge conflicts")
    elif mergeable == "UNKNOWN":
        reasons.append("Merge status is being calculated")
    merge_state = _merge_state_status(pr)
    if merge_state == "BEHIND":
        reasons.append("Branch is behind base; update against the base branch before merging")
    elif merge_state == "BLOCKED":
        reasons.append(
            "Merge blocked by branch protection (missing review decision or "
            "unmet protection rule)"
        )
    return mergeable


# GitHub reports conflicts in two places:
# - mergeable field: set to "CONFLICTING" when a real merge conflict exists.
# - mergeStateStatus field: set to "DIRTY" when the status cache is stale.
# These are the only states where a safe base-ref refresh is the documented
# remedy, so they are the only states for which the stale-conflict advisory
# fires (issue #2368, observed on PR #2334).
_STALE_DIRTY_MERGEABLE = frozenset({"CONFLICTING"})
_STALE_DIRTY_STATE = frozenset({"DIRTY"})


def stale_dirty_suspected(mergeable: str | None, merge_state_status: str | None) -> bool:
    """Report whether a reported conflict may be a stale GitHub cache.

    Returns ``True`` when GitHub reports a DIRTY/CONFLICTING conflict, which is
    the precondition for a stale-mergeability false positive. This is an
    ADVISORY signal only: it does not relax ``CanMerge``. The caller (pr-autofix)
    must confirm against local git, via ``git merge-base --is-ancestor
    origin/<base> HEAD`` plus a clean trial merge, before treating the conflict
    as stale and issuing a safe base-ref refresh. When the local check shows a
    real conflict, the conflict is authoritative and the PR stays blocked.

    Detection works on two fields:
    - mergeable == "CONFLICTING": real merge conflict detected by GitHub
    - mergeStateStatus == "DIRTY": stale cache (status computation incomplete)

    The script is a pure GitHub-API probe with no working tree, so it cannot run
    the ancestry check itself; it surfaces the suspicion and defers the
    git-truth decision to the caller. Safe fallback: absent a local refresh,
    ``CanMerge`` stays ``False``, so a true conflict is never silently merged.
    """
    return (
        (mergeable or "") in _STALE_DIRTY_MERGEABLE
        or (merge_state_status or "") in _STALE_DIRTY_STATE
    )


def _evaluate_review_threads(
    pr: dict, ignore_threads: bool, reasons: list[str],
    owner: str, repo: str, pr_number: int,
) -> tuple[int, int, bool]:
    """Count unresolved threads and append reason.

    Returns ``(unresolved, total, pages_complete)``. ``pages_complete`` is
    True when the inline ``reviewThreads(first: 100)`` page returned every
    thread (``totalCount <= len(nodes)``); False when the page truncated.
    The flag is purely about the inline GraphQL response: even if the
    paginated fallback below produces an exact ``unresolved`` count, a
    truncated inline page means the snapshot is partial and the
    /pr-review completion gate fails closed via ``fetched_pages_complete``.

    The merge-ready GraphQL query embeds a ``reviewThreads(first: 100)``
    inline page to keep the round-trip cheap. When ``totalCount`` exceeds
    the page size, the inline page is a lower bound; we MUST fall back to
    the paginated ``get_unresolved_review_threads`` to avoid the same
    silent-truncation failure mode that motivated PR #1894 for
    ``get_pr_review_threads`` (PR #1887 retrospective). The fallback only
    fires when the page is incomplete, so the fast path stays cheap.
    """
    if ignore_threads:
        return 0, 0, True
    threads = pr.get("reviewThreads", {})
    total_threads = threads.get("totalCount", 0)
    nodes = threads.get("nodes", [])
    pages_complete = total_threads <= len(nodes)

    if total_threads > len(nodes):
        # Calculate inline count as a lower bound before the paginated call.
        # This preserves the "never allow false-zero" invariant per PR #1887
        # retrospective: if the paginated call fails and returns [], we fall
        # back to the inline count rather than incorrectly reporting 0.
        inline_unresolved_count = count_unresolved_threads(nodes)

        # Inline first:100 page truncated. Fall back to paginated helper
        # so unresolved_count is exact, not a lower bound.
        logger.info(
            "op=merge_ready_threads_paginating pr=%d total=%d inline_nodes=%d",
            pr_number, total_threads, len(nodes),
        )
        unresolved_threads = get_unresolved_review_threads(owner, repo, pr_number)
        # Use inline count as floor: if paginated call fails (returns []),
        # fall back to the known lower bound from the inline page.
        unresolved_count = max(inline_unresolved_count, len(unresolved_threads))
    else:
        # Single source of truth for "unresolved" semantics; both branches
        # honor the same rule.
        unresolved_count = count_unresolved_threads(nodes)

    if unresolved_count > 0:
        reasons.append(f"{unresolved_count} unresolved review thread(s)")
    return unresolved_count, total_threads, pages_complete


def _paginate_contexts(
    owner: str, repo: str, pr_number: int, oid: str, start_cursor: str | None,
) -> tuple[list[dict], bool]:
    """Fetch remaining status-check contexts by cursor pagination.

    Returns ``(extra_nodes, pages_complete)``. The boolean is True only
    when the GraphQL pagination terminated normally (``hasNextPage``
    was false on the last page) and the cap was not exhausted.
    """
    extras: list[dict] = []
    cursor = start_cursor
    if not cursor:
        return extras, False
    for _ in range(_CONTEXTS_MAX_PAGES):
        try:
            data = gh_graphql(
                _CONTEXTS_PAGE_QUERY,
                {
                    "owner": owner, "repo": repo, "oid": oid,
                    "number": pr_number, "cursor": cursor,
                },
            )
        except RuntimeError as exc:
            logger.warning(
                "op=merge_ready_contexts_paginate_error pr=%d oid=%s err=%s",
                pr_number, oid, safe_log_str(str(exc)),
            )
            return extras, False
        commit_obj = (data.get("repository") or {}).get("object") or {}
        rollup = commit_obj.get("statusCheckRollup") or {}
        contexts_obj = rollup.get("contexts") or {}
        nodes = contexts_obj.get("nodes") or []
        extras.extend(nodes)
        page_info = contexts_obj.get("pageInfo") or {}
        if not page_info.get("hasNextPage", False):
            return extras, True
        cursor = page_info.get("endCursor")
        if not cursor:
            return extras, False
    return extras, False


def _evaluate_ci_checks(
    pr: dict,
    ignore_ci: bool,
    include_non_required: bool,
    reasons: list[str],
    owner: str = "", repo: str = "", pr_number: int = 0,
) -> tuple[list[str], list[str], list[str], list[str], int, bool, int, bool]:
    """Classify rollup contexts and append CI reasons.

    Returns ``(failed_required, pending_required, failed_non_required,
    pending_non_required, passed_checks, ci_passing, rollup_rows,
    pages_complete)``. ``pages_complete`` is True when every status
    context on the latest commit was retrieved (either the inline
    first:100 page was complete, or paginated follow-up calls exhausted
    the list). False when truncation could not be resolved (paginate
    hit the cap, or a follow-up GraphQL error). A truncated snapshot
    can hide a failing required check, so the /pr-review completion
    gate fails closed via ``fetched_pages_complete``.

    ``owner``, ``repo``, and ``pr_number`` are required for the
    paginated follow-up but default to empty/zero for backward
    compatibility with callers that only need the inline-page slice
    (e.g. unit tests that supply a synthetic PR dict).
    """
    failed_required: list[str] = []
    pending_required: list[str] = []
    failed_non_required: list[str] = []
    pending_non_required: list[str] = []
    skipped_names: list[str] = []
    passed_checks = 0
    ci_passing = True
    rollup_rows = 0
    pages_complete = True

    if ignore_ci:
        return (failed_required, pending_required, failed_non_required,
                pending_non_required, passed_checks, ci_passing,
                rollup_rows, pages_complete)

    commits = pr.get("commits", {}).get("nodes", [])
    if commits:
        commit_obj = commits[0].get("commit", {}) or {}
        oid = commit_obj.get("oid", "")
        rollup = commit_obj.get("statusCheckRollup")
        if rollup:
            contexts_obj = rollup.get("contexts", {}) or {}
            total_contexts = contexts_obj.get("totalCount")
            contexts = list(contexts_obj.get("nodes", []) or [])
            page_info = contexts_obj.get("pageInfo") or {}

            # Inline first:100 page truncated. Paginate to keep the
            # snapshot exact, mirroring the threads-side fallback in
            # _evaluate_review_threads. If pagination fails or hits
            # the cap, pages_complete stays False so the gate fails
            # closed even if the partial set looks clean.
            if (
                page_info.get("hasNextPage", False)
                and owner and repo and pr_number and oid
            ):
                logger.info(
                    "op=merge_ready_contexts_paginating pr=%d total=%s "
                    "inline_nodes=%d",
                    pr_number, total_contexts, len(contexts),
                )
                extras, ok = _paginate_contexts(
                    owner, repo, pr_number, oid,
                    page_info.get("endCursor"),
                )
                contexts.extend(extras)
                if not ok:
                    pages_complete = False
            elif total_contexts is not None:
                pages_complete = total_contexts <= len(contexts)

            rollup_rows = len(contexts)
            _classify_check_contexts(
                contexts,
                failed_required=failed_required,
                pending_required=pending_required,
                failed_non_required=failed_non_required,
                pending_non_required=pending_non_required,
                skipped_names=skipped_names,
            )
            passed_checks = _count_passed_checks(
                contexts,
                blocked=(failed_required + pending_required
                         + failed_non_required + pending_non_required),
                skipped=skipped_names,
            )

    ci_passing = _append_ci_reasons(
        reasons, failed_required, pending_required,
        failed_non_required, pending_non_required, include_non_required,
    )
    return (failed_required, pending_required, failed_non_required,
            pending_non_required, passed_checks, ci_passing,
            rollup_rows, pages_complete)


def _append_ci_reasons(
    reasons: list[str],
    failed_required: list[str], pending_required: list[str],
    failed_non_required: list[str], pending_non_required: list[str],
    include_non_required: bool,
) -> bool:
    """Append human-readable CI reasons for each non-empty bucket.

    Returns ``ci_passing`` (False if any blocking bucket non-empty).
    Required-check failures and pendings always block; non-required block
    only when ``include_non_required`` is set.
    """
    ci_passing = True
    if failed_required:
        reasons.append(
            f"{len(failed_required)} required CI check(s) failed: "
            f"{', '.join(failed_required)}"
        )
        ci_passing = False
    if pending_required:
        reasons.append(
            f"{len(pending_required)} required CI check(s) pending: "
            f"{', '.join(pending_required)}"
        )
        ci_passing = False
    if include_non_required and failed_non_required:
        reasons.append(
            f"{len(failed_non_required)} non-required CI check(s) failed: "
            f"{', '.join(failed_non_required)}"
        )
        ci_passing = False
    if include_non_required and pending_non_required:
        reasons.append(
            f"{len(pending_non_required)} non-required CI check(s) pending: "
            f"{', '.join(pending_non_required)}"
        )
        ci_passing = False
    return ci_passing


def _emit_merge_ready_log(
    pr_number: int, owner: str, repo: str,
    rollup_rows: int, blocked_names: list[str],
    unresolved_threads: int, can_merge: bool, op_start: float,
) -> None:
    """Boundary log: one structured INFO line per check_merge_readiness call."""
    logger.info(
        "op=merge_ready pr=%d owner=%s repo=%s rollup_rows=%d "
        "distinct_blocked=%d unresolved_threads=%d can_merge=%s "
        "duration_ms=%d",
        pr_number, owner, repo, rollup_rows, len(set(blocked_names)),
        unresolved_threads, can_merge,
        int((time.monotonic() - op_start) * 1000),
    )


def _script_commit() -> str:
    """Return the short git SHA of this script's last commit (issue #2443).

    Stamps the readiness verdict with the version of the readiness logic that
    produced it, so a saved CanMerge result can be audited against the exact
    script revision. Returns "unknown" when git is unavailable or the script is
    untracked, for example a shared checkout running an uncommitted copy.
    """

    script = os.path.abspath(__file__)
    try:
        result = subprocess.run(
            ["git", "-C", os.path.dirname(script),
             "log", "-1", "--format=%h", "--", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def check_merge_readiness(
    owner: str,
    repo: str,
    pr_number: int,
    ignore_ci: bool = False,
    ignore_threads: bool = False,
    include_non_required: bool = False,
) -> dict:
    """Check if a PR is ready to merge. Sergeant orchestrator."""
    op_start = time.monotonic()
    pr = _fetch_pr_data(owner, repo, pr_number, op_start)

    reasons: list[str] = []
    merge_state = _merge_state_status(pr)
    mergeable = _evaluate_pr_state(pr, reasons)
    unresolved_count, total_threads, threads_pages_complete = _evaluate_review_threads(
        pr, ignore_threads, reasons, owner, repo, pr_number,
    )
    (failed_required, pending_required, failed_non_required,
     pending_non_required, passed_checks, ci_passing,
     rollup_rows, contexts_pages_complete) = _evaluate_ci_checks(
        pr, ignore_ci, include_non_required, reasons,
        owner=owner, repo=repo, pr_number=pr_number,
    )
    can_merge = len(reasons) == 0
    fetched_pages_complete = threads_pages_complete and contexts_pages_complete
    _emit_merge_ready_log(
        pr_number, owner, repo, rollup_rows,
        failed_required + pending_required
        + failed_non_required + pending_non_required,
        unresolved_count, can_merge, op_start,
    )
    return {
        "Success": True,
        "ScriptCommit": _script_commit(),
        "CanMerge": can_merge,
        "PullRequest": pr_number,
        "Owner": owner,
        "Repo": repo,
        "State": pr["state"],
        "IsDraft": pr.get("isDraft", False),
        "Mergeable": mergeable,
        "MergeStateStatus": merge_state,
        "StaleDirtySuspected": stale_dirty_suspected(
            mergeable or "", merge_state
        ),
        "UnresolvedThreads": unresolved_count,
        "TotalThreads": total_threads,
        "FailedRequiredChecks": failed_required,
        "PendingRequiredChecks": pending_required,
        "FailedNonRequiredChecks": failed_non_required,
        "PendingNonRequiredChecks": pending_non_required,
        "PassedChecks": passed_checks,
        "CIPassing": ci_passing,
        "IncludeNonRequired": include_non_required,
        "fetched_pages_complete": fetched_pages_complete,
        "Reasons": reasons,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check if a PR is ready to merge.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True,
        help="PR number",
    )
    parser.add_argument(
        "--ignore-ci", action="store_true",
        help="Skip CI check verification",
    )
    parser.add_argument(
        "--ignore-threads", action="store_true",
        help="Skip unresolved thread check",
    )
    parser.add_argument(
        "--include-non-required", action="store_true",
        help="Non-required check failures also block merge",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    result = check_merge_readiness(
        owner,
        repo,
        args.pull_request,
        ignore_ci=args.ignore_ci,
        ignore_threads=args.ignore_threads,
        include_non_required=args.include_non_required,
    )

    print(json.dumps(result, indent=2))

    if result["CanMerge"]:
        print(f"PR #{args.pull_request} is READY to merge", file=sys.stderr)
        return 0

    print(f"PR #{args.pull_request} is NOT ready to merge", file=sys.stderr)
    for reason in result["Reasons"]:
        print(f"  - {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
