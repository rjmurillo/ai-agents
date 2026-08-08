#!/usr/bin/env python3
# taste-lint: ignore file-size -- extraction would scatter cohesive logic
"""Get CI check status for a GitHub Pull Request.

Retrieves CI check information using GraphQL statusCheckRollup API.
Returns structured JSON with check states, conclusions, and summary counts.
Supports polling until checks complete and filtering to required checks only.

Exit codes follow ADR-035:
    0 - All checks passing (or skipped/pending)
    1 - One or more checks failed
    2 - PR not found
    3 - API error
    7 - Timeout reached (with --wait)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from typing import Any

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
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

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
)
from github_core.checks_rollup import (
    extract_workflow_run_number,
    partition_rows_by_run,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------

_CHECKS_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            baseRefName
            mergeable
            mergeStateStatus
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
                                        detailsUrl
                                        checkSuite { app { databaseId } }
                                        isRequired(pullRequestNumber: $number)
                                    }
                                    ... on StatusContext {
                                        __typename
                                        context
                                        state
                                        targetUrl
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

_CHECKS_PAGE_QUERY = """\
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
                                detailsUrl
                                checkSuite { app { databaseId } }
                                isRequired(pullRequestNumber: $number)
                            }
                            ... on StatusContext {
                                __typename
                                context
                                state
                                targetUrl
                                isRequired(pullRequestNumber: $number)
                            }
                        }
                    }
                }
            }
        }
    }
}"""

_CONTEXTS_MAX_PAGES = 50
_BLOCKING_MERGE_STATES = {"CONFLICTING", "UNKNOWN"}
_BLOCKING_MERGE_STATE_STATUSES = {"DIRTY", "UNKNOWN"}

# Pending statuses for CheckRun
_PENDING_STATUSES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}
# Passing conclusions for CheckRun
_PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
# Failing conclusions for CheckRun
_FAILING_CONCLUSIONS = {
    "FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED",
    "STALE", "STARTUP_FAILURE",
}



# ---------------------------------------------------------------------------
# Ruleset required-context fetch (#4359)
# ---------------------------------------------------------------------------


def fetch_ruleset_required_contexts(
    owner: str,
    repo: str,
    base_branch: str,
) -> list[dict[str, Any]]:
    """Return required check identities from branch rulesets.

    Uses the REST rules/branches endpoint to find the ground-truth set of
    required status checks independent of whether any check has reported.
    A check that never ran produces no row in statusCheckRollup and has no
    isRequired annotation; the only way to detect it is to diff the ruleset
    list against the reported set.

    Raises RuntimeError when the ruleset inventory cannot be read. Missing
    required checks cannot be detected without this inventory, so callers
    must not report the PR as passing when the lookup fails.
    """
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/rules/branches/{base_branch}",
            "--jq",
            (
                "[.[]"
                "| select(.type==\"required_status_checks\")"
                "| .parameters.required_status_checks[]"
                "| {context: .context, integration_id: .integration_id}]"
            ),
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"gh api exited {result.returncode}"
        raise RuntimeError(f"Required-check ruleset lookup failed: {detail}")
    try:
        raw = result.stdout.strip()
        if not raw:
            raise ValueError("empty response")
        items = json.loads(raw)
        if not isinstance(items, list):
            raise TypeError("expected a list")
        return [
            {
                "Context": str(item["context"]),
                "IntegrationId": item.get("integration_id"),
            }
            for item in items
            if isinstance(item, dict) and item.get("context")
        ]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Required-check ruleset response was invalid: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Check normalization
# ---------------------------------------------------------------------------


def normalize_check(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a GraphQL context node to a normalized check info dict."""
    typename = ctx.get("__typename")

    if typename == "CheckRun":
        status = ctx.get("status", "")
        conclusion = ctx.get("conclusion", "")
        return {
            "Name": ctx.get("name", ""),
            "Type": "CheckRun",
            "State": status,
            "Conclusion": conclusion,
            "DetailsUrl": ctx.get("detailsUrl", ""),
            "IntegrationId": (
                ((ctx.get("checkSuite") or {}).get("app") or {}).get("databaseId")
            ),
            "IsRequired": ctx.get("isRequired", False),
            "IsPending": status in _PENDING_STATUSES,
            "IsPassing": conclusion in _PASSING_CONCLUSIONS,
            "IsFailing": conclusion in _FAILING_CONCLUSIONS,
        }

    if typename == "StatusContext":
        state = ctx.get("state", "")
        return {
            "Name": ctx.get("context", ""),
            "Type": "StatusContext",
            "State": state,
            "Conclusion": state,
            "DetailsUrl": ctx.get("targetUrl", ""),
            "IntegrationId": None,
            "IsRequired": ctx.get("isRequired", False),
            "IsPending": state in ("PENDING", "EXPECTED"),
            "IsPassing": state == "SUCCESS",
            "IsFailing": state in ("FAILURE", "ERROR"),
        }

    return None


# ---------------------------------------------------------------------------
# Deduplication of superseded check runs
# ---------------------------------------------------------------------------
#
# GitHub keeps every check run for a check name on one commit, including older
# runs that a newer run superseded (a re-run, or a debounce that cancels the
# stale run). A stale FAILURE left alongside a fresh SUCCESS inflated
# FailedCount for PR #2201 even though test_pr_merge_ready.py reported the PR
# ready. Refs Issue #2208.
#
# This script leaves OverallState as GitHub's rollup value. Deduplication only
# affects the per-check rows and derived counts, such as FailedCount. The
# When each duplicate exposes a workflow run id, the latest run decides. Unknown
# provenance keeps the previous precedence behavior: passing beats failing,
# failing beats pending. Any pending signal is still retained for wait polling,
# including when a same-name passing run is present.
#
# Stricter/looser/different than canonical: test_pr_merge_ready.py treats a
# CANCELLED-only group as no-opinion (SKIP) so it neither blocks nor counts as
# passed. Here, normalize_check already maps CANCELLED into IsFailing (it is in
# _FAILING_CONCLUSIONS), so a CANCELLED-only group surfaces as a failing check.
# That preserves this script's long-standing CANCELLED semantics; the dedupe
# only collapses duplicate names and uses workflow run ids when every duplicate
# exposes one.

# Precedence key: lower sorts first, so the winning entry is the minimum.
_PASSING_RANK = 0
_FAILING_RANK = 1
_PENDING_RANK = 2
_UNKNOWN_RANK = 3
_TYPE_RANK = {"CheckRun": 0, "StatusContext": 1}


def _check_rank(check: dict[str, Any]) -> int:
    """Rank a normalized check by precedence: passing < failing < pending."""
    if check.get("IsPassing"):
        return _PASSING_RANK
    if check.get("IsFailing"):
        return _FAILING_RANK
    if check.get("IsPending"):
        return _PENDING_RANK
    return _UNKNOWN_RANK


def _dedupe_rank(check: dict[str, Any]) -> tuple[int, int]:
    """Rank by source type first, then verdict precedence."""
    check_type = str(check.get("Type") or "")
    return (_TYPE_RANK.get(check_type, 2), _check_rank(check))


def _check_workflow_run_number(check: dict[str, Any]) -> int | None:
    """Return a CheckRun workflow run id when the details URL exposes one."""
    if check.get("Type") != "CheckRun":
        return None
    details_url = check.get("DetailsUrl")
    run_number = extract_workflow_run_number(
        details_url if isinstance(details_url, str) else None
    )
    return run_number if isinstance(run_number, int) else None


def _select_cross_run_winner(candidates: list[dict[Any, Any]]) -> dict[Any, Any]:
    """Pick the latest workflow run when all candidates have run provenance."""
    check_run_pairs = [
        (check, _check_workflow_run_number(check))
        for check in candidates
        if check.get("Type") == "CheckRun"
    ]
    if check_run_pairs and all(
        run_number is not None for _, run_number in check_run_pairs
    ):
        known_run_numbers = [
            run_number
            for _, run_number in check_run_pairs
            if run_number is not None
        ]
        latest_run = max(known_run_numbers)
        latest_candidates = [
            check for check, run_number in check_run_pairs
            if run_number == latest_run
        ]
        return sorted(latest_candidates, key=_dedupe_rank)[0]
    return sorted(candidates, key=_dedupe_rank)[0]


def _collapse_same_run_siblings(rows: list[dict[Any, Any]]) -> list[dict[Any, Any]]:
    """Reduce each workflow run's same-named rows to one representative row.

    Within one run, two rows sharing a check name are concurrent siblings, not
    a supersession, so a failing sibling must win over a passing one. Across
    runs the caller uses workflow run recency when every candidate exposes it.

    Refs issue #4499.
    """
    representatives: list[dict[Any, Any]] = []
    for group in partition_rows_by_run(rows, "DetailsUrl"):
        if len(group) == 1:
            representatives.append(group[0])
            continue
        failing = [row for row in group if row.get("IsFailing")]
        pool = failing if failing else group
        representative = {
            **sorted(pool, key=_dedupe_rank)[0],
            "IsPending": any(row.get("IsPending") for row in group),
        }
        representatives.append(representative)
    return representatives


def dedupe_checks(
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse multiple runs of one check identity to the winning entry.

    Groups by ``Name`` plus GitHub App integration id and keeps the latest
    workflow-run entry when all CheckRun candidates expose run ids. Unknown
    provenance keeps the previous precedence behavior. Required-check status
    is retained when any duplicate row for that identity is required.

    Two rows of the SAME workflow run are collapsed first, pessimistically: a
    failing sibling beats a passing one because both jobs really ran and one
    really failed. Only then does cross-run precedence pick the winner.
    """
    integration_ids_by_name: dict[str, set[int]] = {}
    for check in checks:
        integration_id = check.get("IntegrationId")
        if integration_id is not None:
            name = str(check.get("Name") or "")
            integration_ids_by_name.setdefault(name, set()).add(integration_id)

    rows_by_identity: dict[
        tuple[str, int | None],
        list[dict[str, Any]],
    ] = {}
    required_by_identity: dict[tuple[str, int | None], bool] = {}
    order: list[tuple[str, int | None]] = []
    for check in checks:
        name_value = check.get("Name")
        name = "" if name_value is None else str(name_value)
        integration_id = check.get("IntegrationId")
        known_ids = integration_ids_by_name.get(str(name), set())
        if check.get("Type") == "StatusContext" and len(known_ids) == 1:
            integration_id = next(iter(known_ids))
        identity = (name, integration_id)
        required_by_identity[identity] = required_by_identity.get(
            identity, False
        ) or bool(
            check.get("IsRequired")
        )
        if identity not in rows_by_identity:
            rows_by_identity[identity] = []
            order.append(identity)
        rows_by_identity[identity].append(check)

    deduped = []
    for identity in order:
        candidates = _collapse_same_run_siblings(rows_by_identity[identity])
        best = dict(_select_cross_run_winner(candidates))
        check_run_pairs = [
            (check, _check_workflow_run_number(check))
            for check in candidates
            if check.get("Type") == "CheckRun"
        ]
        has_complete_run_provenance = (
            len(check_run_pairs) == len(candidates)
            and all(run_number is not None for _, run_number in check_run_pairs)
        )
        if not has_complete_run_provenance:
            best["IsPending"] = any(
                check.get("IsPending") for check in candidates
            )
        winner = {
            **best,
            "IsRequired": required_by_identity[identity],
        }
        deduped.append(winner)
    return deduped


# ---------------------------------------------------------------------------
# Query and parse
# ---------------------------------------------------------------------------


def _paginate_contexts(
    owner: str,
    repo: str,
    pr_number: int,
    oid: str,
    start_cursor: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch remaining status-check contexts by cursor pagination."""
    if not start_cursor:
        return [], False

    extras: list[dict[str, Any]] = []
    cursor = start_cursor
    for _ in range(_CONTEXTS_MAX_PAGES):
        try:
            data = gh_graphql(
                _CHECKS_PAGE_QUERY,
                {
                    "owner": owner,
                    "repo": repo,
                    "oid": oid,
                    "number": pr_number,
                    "cursor": cursor,
                },
            )
        except RuntimeError:
            return extras, False
        commit_obj = (data.get("repository") or {}).get("object") or {}
        rollup = commit_obj.get("statusCheckRollup") or {}
        contexts_obj = rollup.get("contexts") or {}
        extras.extend(contexts_obj.get("nodes") or [])
        page_info = contexts_obj.get("pageInfo") or {}
        if not page_info.get("hasNextPage", False):
            return extras, True
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            return extras, False
        cursor = next_cursor

    return extras, False


def fetch_checks(
    owner: str, repo: str, pr_number: int,
) -> dict[str, Any]:
    """Execute GraphQL query and return parsed result."""
    try:
        data = gh_graphql(
            _CHECKS_QUERY,
            {"owner": owner, "repo": repo, "number": pr_number},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg or "not found" in msg:
            return {"Error": "NotFound", "Message": f"PR #{pr_number} not found in {owner}/{repo}"}
        return {"Error": "ApiError", "Message": f"GraphQL query failed: {msg}"}

    pr = data.get("repository", {}).get("pullRequest")
    if pr is None:
        return {"Error": "NotFound", "Message": "PR not found in response"}

    mergeable = pr.get("mergeable")
    merge_state_status = pr.get("mergeStateStatus")
    merge_state = "UNKNOWN" if mergeable is None else str(mergeable)
    base_branch = pr.get("baseRefName", "")

    commits = pr.get("commits", {}).get("nodes", [])
    if not commits:
        return {
            "Number": pr.get("number"),
            "BaseBranch": base_branch,
            "MergeState": merge_state,
            "MergeStateStatus": merge_state_status,
            "Checks": [],
            "OverallState": "UNKNOWN",
            "HasChecks": False,
        }

    commit = commits[0]
    commit_obj = commit.get("commit", {}) or {}
    rollup = commit_obj.get("statusCheckRollup")
    if not rollup:
        return {
            "Number": pr.get("number"),
            "BaseBranch": base_branch,
            "MergeState": merge_state,
            "MergeStateStatus": merge_state_status,
            "Checks": [],
            "OverallState": "UNKNOWN",
            "HasChecks": False,
        }

    overall_state = rollup.get("state", "UNKNOWN")
    contexts_obj = rollup.get("contexts", {}) or {}
    context_nodes = list(contexts_obj.get("nodes", []) or [])
    page_info = contexts_obj.get("pageInfo") or {}
    total_contexts = contexts_obj.get("totalCount")
    pages_complete = True
    if page_info.get("hasNextPage", False):
        extras, pages_complete = _paginate_contexts(
            owner,
            repo,
            pr_number,
            commit_obj.get("oid", ""),
            page_info.get("endCursor"),
        )
        context_nodes.extend(extras)
    elif total_contexts is not None:
        pages_complete = total_contexts <= len(context_nodes)

    checks = []
    for ctx in context_nodes:
        check = normalize_check(ctx)
        if check:
            checks.append(check)

    checks = dedupe_checks(checks)

    return {
        "Number": pr.get("number"),
        "BaseBranch": pr.get("baseRefName", ""),
        "MergeState": merge_state,
        "MergeStateStatus": merge_state_status,
        "Checks": checks,
        "OverallState": overall_state,
        "HasChecks": True,
        "ChecksIncomplete": not pages_complete,
    }


def build_output(
    check_data: dict[str, Any],
    owner: str,
    repo: str,
    required_only: bool = False,
    ruleset_required: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the final output object from check data.

    Groups checks by name and ORs the required status across all rows
    for each name, matching test_pr_merge_ready.py semantics. Returns
    structured lists of pending and failed required checks.

    ruleset_required: context and integration identities declared by the
    branch ruleset. Matching both fields prevents a same-name check from a
    different GitHub App from satisfying the requirement.
    """
    checks_value = check_data.get("Checks")
    if checks_value is None:
        checks = []
    elif not isinstance(checks_value, list):
        raise ValueError("Checks must be a list")
    else:
        checks = checks_value

    filtered_checks = dedupe_checks(checks)

    def matches_requirement(
        check: dict[str, Any],
        requirement: dict[str, Any],
    ) -> bool:
        if check.get("Name") != requirement.get("Context"):
            return False
        integration_id = requirement.get("IntegrationId")
        return (
            integration_id is None
            or check.get("IntegrationId") == integration_id
        )

    for check in filtered_checks:
        check["IsRequired"] = bool(check.get("IsRequired")) or any(
            matches_requirement(check, requirement)
            for requirement in ruleset_required or []
        )

    if required_only:
        filtered_checks = [
            check for check in filtered_checks if check.get("IsRequired")
        ]

    failed_count = sum(1 for c in filtered_checks if c.get("IsFailing"))
    pending_count = sum(1 for c in filtered_checks if c.get("IsPending"))
    passed_count = sum(1 for c in filtered_checks if c.get("IsPassing"))

    has_checks = check_data.get("HasChecks", False)
    checks_incomplete = bool(check_data.get("ChecksIncomplete", False))
    if "MergeState" in check_data:
        merge_state_value = check_data.get("MergeState")
        merge_state = "UNKNOWN" if merge_state_value is None else str(merge_state_value)
    else:
        merge_state = "MERGEABLE"
    # Same fail-closed shape as MergeState above. An explicit None means the
    # GraphQL field came back null, so the state is unknown and must block; a
    # missing key means a legacy caller that never queried the field, which
    # keeps the historical CLEAN default.
    if "MergeStateStatus" in check_data:
        merge_state_status_value = check_data.get("MergeStateStatus")
        merge_state_status = (
            "UNKNOWN" if merge_state_status_value is None else str(merge_state_status_value)
        )
    else:
        merge_state_status = "CLEAN"
    merge_ref_usable = (
        merge_state not in _BLOCKING_MERGE_STATES
        and merge_state_status not in _BLOCKING_MERGE_STATE_STATUSES
    )
    merge_state_warning = ""
    if merge_state == "CONFLICTING":
        merge_state_warning = (
            "PR merge ref cannot be built because GitHub reports merge conflicts; "
            "most workflows may not have run"
        )
    elif merge_state_status == "DIRTY":
        merge_state_warning = (
            "PR merge ref cannot be built because GitHub reports dirty merge state; "
            "most workflows may not have run"
        )
    elif merge_state == "UNKNOWN":
        merge_state_warning = (
            "PR merge state is unknown; do not treat the current check set as complete"
        )
    elif merge_state_status == "UNKNOWN":
        merge_state_warning = (
            "PR merge state status is unknown; do not treat the current check set as complete"
        )

    # Set-difference: required contexts from the ruleset that never appeared
    # in the statusCheckRollup at all.  A check that never ran has no row and
    # no isRequired annotation; absence is the only signal.
    missing_required: list[str] = []
    if ruleset_required:
        missing_required = sorted(
            {
                str(requirement["Context"])
                for requirement in ruleset_required
                if not any(
                    matches_requirement(check, requirement)
                    for check in filtered_checks
                )
            }
        )

    all_passing = (
        has_checks
        and len(filtered_checks) > 0
        and failed_count == 0
        and pending_count == 0
        and not checks_incomplete
        and merge_ref_usable
        and not missing_required
    )

    # Extract lists of pending and failed required checks for structured
    # output so downstream agents can distinguish the two categories.
    pending_required = sorted({
        str(check.get("Name", ""))
        for check in filtered_checks
        if check.get("IsRequired")
        and check.get("IsPending")
        and not check.get("IsPassing")
    })
    failed_required = sorted({
        str(check.get("Name", ""))
        for check in filtered_checks
        if check.get("IsRequired") and check.get("IsFailing")
    })

    return {
        "Success": True,
        "Number": check_data.get("Number"),
        "Owner": owner,
        "Repo": repo,
        "OverallState": check_data.get("OverallState", "UNKNOWN"),
        "MergeState": merge_state,
        "MergeStateStatus": merge_state_status,
        "MergeRefUsable": merge_ref_usable,
        "MergeStateWarning": merge_state_warning,
        "HasChecks": has_checks,
        "Checks": [
            {
                "Name": c["Name"],
                "State": c["State"],
                "Conclusion": c["Conclusion"],
                "DetailsUrl": c["DetailsUrl"],
                "IntegrationId": c.get("IntegrationId"),
                "IsRequired": c["IsRequired"],
            }
            for c in filtered_checks
        ],
        "FailedCount": failed_count,
        "PendingCount": pending_count,
        "PassedCount": passed_count,
        "AllPassing": all_passing,
        # True only when --wait exhausted its budget while the checks rollup
        # was still empty (transient GraphQL race), distinguishing it from a
        # PR that genuinely has no checks (HasChecks False, ChecksIncomplete
        # False). See #2304. Set authoritatively by main() under --wait.
        "ChecksIncomplete": checks_incomplete,
        # Lists of required check names by verdict, for structured output.
        # Helps downstream agents distinguish pending required checks from
        # failed ones and from non-required checks.
        "PendingRequiredChecks": pending_required,
        "FailedRequiredChecks": failed_required,
        # Checks required by the branch ruleset that produced no row in the
        # status check rollup (i.e. never ran). Populated when the
        # rules/branches endpoint is reachable; empty list when not.
        "MissingRequiredChecks": missing_required,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get CI check status for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True,
        help="PR number",
    )
    parser.add_argument(
        "--wait", action="store_true",
        help="Poll until all checks complete or timeout",
    )
    parser.add_argument(
        "--timeout-seconds", type=int, default=300,
        help="Maximum wait time in seconds (default: 300)",
    )
    parser.add_argument(
        "--required-only", action="store_true",
        help="Filter output to required checks only",
    )
    add_output_format_arg(parser)
    return parser


def _resolve_status(
    output: dict[str, Any],
    timeout_seconds: int,
    timed_out_pending: bool,
    checks_incomplete: bool,
) -> tuple[str, str]:
    """Return (human_summary, status) for the final check output."""
    number = output["Number"]
    merge_state_warning = output.get("MergeStateWarning")
    if merge_state_warning:
        return f"PR #{number}: {merge_state_warning}", "FAIL"
    if checks_incomplete:
        return (
            f"PR #{number}: checks still unavailable after {timeout_seconds}s "
            "(empty rollup; not treated as passing)",
            "WARNING",
        )
    missing = output.get("MissingRequiredChecks") or []
    if missing:
        return (
            f"PR #{number}: {len(missing)} required check(s) never reported "
            f"(MISSING: {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''})",
            "FAIL",
        )
    if output["FailedCount"] > 0:
        return f"PR #{number}: {output['FailedCount']} check(s) failed", "FAIL"
    if timed_out_pending:
        return (
            f"Timeout: {output['PendingCount']} check(s) still pending "
            f"after {timeout_seconds} seconds",
            "WARNING",
        )
    if output["PendingCount"] > 0:
        return (
            f"PR #{number}: {output['PendingCount']} check(s) still pending",
            "WARNING",
        )
    return f"PR #{number}: All {output['PassedCount']} check(s) passing", "PASS"


def _check_data_error_exit(
    check_data: dict[str, Any],
    fmt: str,
    pr: int,
) -> int | None:
    """Return an exit code if check_data contains an error, else None."""
    if check_data.get("Error") == "NotFound":
        write_skill_error(
            check_data["Message"],
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name="get_pr_checks.py",
            extra={"Number": pr},
        )
        return 2
    if check_data.get("Error") == "ApiError":
        write_skill_error(
            check_data["Message"],
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="get_pr_checks.py",
            extra={"Number": pr},
        )
        return 3
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    fmt = get_output_format(args.output_format)

    start_time = time.monotonic()
    max_iterations = math.ceil(args.timeout_seconds / 10)
    iteration = 0
    settled = False
    checks_incomplete = False
    ruleset_required: list[dict[str, Any]] = []

    while True:
        iteration += 1
        check_data = fetch_checks(owner, repo, args.pull_request)

        # Handle errors
        rc = _check_data_error_exit(check_data, fmt, args.pull_request)
        if rc is not None:
            return rc

        # Fetch ruleset required contexts once. The base branch does not
        # change across poll iterations.
        if iteration == 1:
            base_branch = check_data.get("BaseBranch", "")
            if base_branch:
                try:
                    ruleset_required = fetch_ruleset_required_contexts(
                        owner, repo, base_branch
                    )
                except RuntimeError as exc:
                    write_skill_error(
                        str(exc),
                        3,
                        error_type="ApiError",
                        output_format=fmt,
                        script_name="get_pr_checks.py",
                        extra={"Number": args.pull_request},
                    )
                    return 3

        output = build_output(
            check_data, owner, repo, args.required_only,
            ruleset_required=ruleset_required,
        )
        checks_incomplete = checks_incomplete or bool(
            output.get("ChecksIncomplete", False)
        )

        # Under --wait, an empty present rollup is usually a transient GraphQL
        # race, not "no checks configured". Keep polling only when GitHub
        # returned a rollup object with no contexts; a missing rollup is a real
        # no-checks PR and must settle immediately. See #2304.
        empty_present_rollup = output["HasChecks"] and not output["Checks"]
        waiting_on_empty = args.wait and empty_present_rollup

        # Done when not waiting, or settled: nothing pending and not an empty
        # rollup we are still waiting on.
        if not args.wait or (output["PendingCount"] == 0 and not waiting_on_empty):
            settled = True
            break

        # Stop polling on timeout or iteration budget exhaustion.
        elapsed = time.monotonic() - start_time
        if elapsed >= args.timeout_seconds or iteration >= max_iterations:
            # If checks never populated, the rollup raced; tag the result so
            # callers distinguish transient emptiness from a real no-checks PR.
            if waiting_on_empty:
                checks_incomplete = True
            break

        time.sleep(10)

    output["ChecksIncomplete"] = checks_incomplete
    timed_out_pending = not settled and output["PendingCount"] > 0

    # Determine status for human output
    summary, status = _resolve_status(
        output, args.timeout_seconds, timed_out_pending, checks_incomplete
    )

    write_skill_output(
        output,
        output_format=fmt,
        human_summary=summary,
        status=status,
        script_name="get_pr_checks.py",
    )

    return _exit_code(output, checks_incomplete, timed_out_pending)


def _exit_code(
    output: dict[str, Any],
    checks_incomplete: bool,
    timed_out_pending: bool,
) -> int:
    missing = output.get("MissingRequiredChecks") or []
    if output["FailedCount"] > 0 or missing:
        return 1
    if not output.get("MergeRefUsable", True):
        return 1
    if checks_incomplete or timed_out_pending:
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
