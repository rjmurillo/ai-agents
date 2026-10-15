#!/usr/bin/env python3
# mypy: disable-error-code="arg-type,assignment,no-any-return,type-arg,type-var", follow-imports=skip
"""Get CI check status for a GitHub Pull Request.

Retrieves CI check information using GraphQL statusCheckRollup API. When
GraphQL refuses with a rate-limit body, it reads the same checks over REST
(check runs and commit statuses) and marks required checks from the branch
ruleset. Output field DataSource says which transport answered. On REST,
--required-only exits 3 when the ruleset lists no required checks. Classic
branch protection is not read by the ruleset lookup, so a failing or pending row
outside the ruleset is kept under --required-only and RequiredState reads UNKNOWN,
not SUCCESS.
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
import contextlib
import io
import math
import os
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
    is_rate_limit_refusal,
    resolve_repo_params,
)
from github_core.checks_rest import (
    PullRequestNotFoundError,
    fetch_checks_rest,
    mark_required_from_ruleset,
)
from github_core.checks_rollup import (
    MISSING_GRACE_SECONDS,
    current_run_keys,
    extract_required_check_lists,
    extract_workflow_run_number,
    fetch_ruleset_required_contexts,
    find_missing_required,
    group_checks_by_name,
    missing_checks_queued,
    partition_rows_by_run,
)
from github_core.not_found import is_pr_not_found
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
                        committedDate
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
                                        checkSuite {
                                            workflowRun {
                                                databaseId
                                                runAttempt
                                                event
                                            }
                                        }
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
                                checkSuite {
                                    workflowRun {
                                        databaseId
                                        runAttempt
                                        event
                                    }
                                }
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
# The agent tool call that wraps this script is killed at 600 seconds, so a
# --wait budget above this leaves no room for the final poll and the output.
MAX_WAIT_TIMEOUT_SECONDS = 570
# Data keys of a successful run. Failure envelopes carry the same keys so a
# caller that pipes json output never hits a KeyError on a failed run.
_DATA_KEYS = (
    "Success",
    "Number",
    "Owner",
    "Repo",
    "BaseBranch",
    "AllState",
    "RequiredState",
    "MergeState",
    "MergeStateStatus",
    "MergeRefUsable",
    "MergeStateWarning",
    "HasChecks",
    "DataSource",
    "Checks",
    "FailedCount",
    "PendingCount",
    "PassedCount",
    "AllPassing",
    "ChecksIncomplete",
    "PendingRequiredChecks",
    "FailedRequiredChecks",
    "MissingRequiredChecks",
    "MissingRequiredQueued",
    "HeadCommittedAt",
)
# Exit code to Error.Type for failures raised as SystemExit before any query.
_PREFLIGHT_ERROR_TYPES = {3: "ApiError", 4: "AuthError"}
_MISSING_RECOVERY_HINT = (
    "Recovery: close and reopen the PR to re-fire pull_request workflows "
    "(see fix-ci.md, 'Required check never reported')."
)

# Pending statuses for CheckRun
_PENDING_STATUSES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}
# Passing conclusions for CheckRun
_PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
# Failing conclusions for CheckRun
_FAILING_CONCLUSIONS = {
    "FAILURE",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STALE",
    "STARTUP_FAILURE",
}


# ---------------------------------------------------------------------------
# Check normalization
# ---------------------------------------------------------------------------


def normalize_check(ctx: dict) -> dict | None:
    """Convert a GraphQL context node to a normalized check info dict."""
    typename = ctx.get("__typename")

    if typename == "CheckRun":
        status = ctx.get("status", "")
        conclusion = ctx.get("conclusion", "")
        workflow_run = (ctx.get("checkSuite") or {}).get("workflowRun") or {}
        return {
            "Name": ctx.get("name", ""),
            "Type": "CheckRun",
            "State": status,
            "Conclusion": conclusion,
            "DetailsUrl": ctx.get("detailsUrl", ""),
            "WorkflowRunId": workflow_run.get("databaseId"),
            "WorkflowRunAttempt": workflow_run.get("runAttempt"),
            "WorkflowEvent": workflow_run.get("event"),
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
# AllState is GitHub's rollup value, left unchanged. Deduplication only
# affects the per-check rows and derived counts, such as FailedCount and
# RequiredState. When each duplicate exposes a workflow run id, the latest run
# of each triggering event is current and the worst current state decides.
# Unknown provenance keeps the previous precedence behavior: passing beats
# failing, failing beats pending. Any pending signal is still retained for
# wait polling, including when a same-name passing run is present.
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


def _check_rank(check: dict) -> int:
    """Rank a normalized check by precedence: passing < failing < pending."""
    if check.get("IsPassing"):
        return _PASSING_RANK
    if check.get("IsFailing"):
        return _FAILING_RANK
    if check.get("IsPending"):
        return _PENDING_RANK
    return _UNKNOWN_RANK


def _dedupe_rank(check: dict) -> tuple[int, int]:
    """Rank by source type first, then verdict precedence."""
    return (_TYPE_RANK.get(check.get("Type"), 2), _check_rank(check))


def _check_workflow_key(check: dict) -> tuple[int, int] | None:
    """Return the Actions workflow run and attempt identity."""
    if check.get("Type") != "CheckRun":
        return None
    run_number = check.get("WorkflowRunId")
    if run_number is None:
        run_number = extract_workflow_run_number(check.get("DetailsUrl"))
    if run_number is None:
        return None
    attempt = check.get("WorkflowRunAttempt")
    return int(run_number), int(attempt) if attempt is not None else 1


def _cross_event_rank(check: dict) -> int:
    """Rank current runs of different events: failing, pending, unknown, passing."""
    order = {
        _FAILING_RANK: 0,
        _PENDING_RANK: 1,
        _UNKNOWN_RANK: 2,
        _PASSING_RANK: 3,
    }
    return order[_check_rank(check)]


def _select_cross_run_winner(candidates: list[dict[Any, Any]]) -> dict[Any, Any]:
    """Pick the current runs when all candidates have run provenance.

    The newest run of each triggering event is current, because the ruleset
    evaluates the ``pull_request`` and ``push`` runs of one head SHA. When
    several events are current, the worst state wins so a red run from one
    event is not hidden by a green run from another.
    """
    check_run_pairs = [
        (check, _check_workflow_key(check))
        for check in candidates
        if check.get("Type") == "CheckRun"
    ]
    if check_run_pairs and all(run_key is not None for _, run_key in check_run_pairs):
        current = current_run_keys(
            [(run_key, check.get("WorkflowEvent")) for check, run_key in check_run_pairs]
        )
        current_candidates = [check for check, run_key in check_run_pairs if run_key in current]
        return sorted(current_candidates, key=_cross_event_rank)[0]
    return sorted(candidates, key=_dedupe_rank)[0]


def _collapse_same_run_siblings(rows: list[dict[Any, Any]]) -> list[dict[Any, Any]]:
    """Reduce each workflow run's same-named rows to one representative row.

    Within one run, two rows sharing a check name are concurrent siblings, not
    a supersession, so a failing sibling must win over a passing one. Across
    runs the caller uses workflow run recency when every candidate exposes it.

    Refs issue #4499.
    """
    representatives: list[dict[Any, Any]] = []
    for group in partition_rows_by_run(
        rows,
        "DetailsUrl",
        "WorkflowRunId",
        "WorkflowRunAttempt",
    ):
        if len(group) == 1:
            representatives.append(
                {
                    **group[0],
                    "_RunIsRequired": bool(group[0].get("IsRequired")),
                }
            )
            continue
        failing = [row for row in group if row.get("IsFailing")]
        pool = failing if failing else group
        representatives.append(
            {
                **sorted(pool, key=_dedupe_rank)[0],
                "_RunIsRequired": any(row.get("IsRequired") for row in group),
            }
        )
    return representatives


def dedupe_checks(checks: list[dict]) -> list[dict]:
    """Collapse multiple runs of one check name to the winning entry.

    Groups by ``Name`` and keeps the latest workflow-run entry when all
    CheckRun candidates expose run ids. Unknown provenance keeps the previous
    precedence behavior. The first-seen order of surviving names is preserved.
    Required-check status is retained when any duplicate row for a name is
    required.

    Two rows of the SAME workflow run are collapsed first, pessimistically: a
    failing sibling beats a passing one because both jobs really ran and one
    really failed. Only then does cross-run precedence pick the winner.
    """
    rows_by_name: dict[str, list[dict]] = {}
    required_by_name: dict[str, bool] = {}
    pending_by_name: dict[str, bool] = {}
    order: list[str] = []
    for check in checks:
        name_value = check.get("Name")
        name = "" if name_value is None else name_value
        required_by_name[name] = required_by_name.get(name, False) or bool(check.get("IsRequired"))
        pending_by_name[name] = pending_by_name.get(name, False) or bool(check.get("IsPending"))
        if name not in rows_by_name:
            rows_by_name[name] = []
            order.append(name)
        rows_by_name[name].append(check)

    deduped = []
    for name in order:
        candidates = _collapse_same_run_siblings(rows_by_name[name])
        if required_by_name[name]:
            candidates = [check for check in candidates if check.get("_RunIsRequired")]
        best = _select_cross_run_winner(candidates)
        winner = {
            **best,
            "IsRequired": required_by_name[name],
        }
        winner.pop("_RunIsRequired", None)
        winner["IsPending"] = pending_by_name[name]
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
) -> tuple[list[dict], bool]:
    """Fetch remaining status-check contexts by cursor pagination."""
    if not start_cursor:
        return [], False

    extras: list[dict] = []
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
        cursor = page_info.get("endCursor")
        if not cursor:
            return extras, False

    return extras, False


def _overall_state(checks: list[dict]) -> str:
    """Derive a rollup state from normalized checks, for the REST transport.

    GraphQL reports GitHub's own rollup state. REST has no such field, so this
    applies the same precedence: a failing row beats a pending row beats success.
    """
    if not checks:
        return "UNKNOWN"
    if any(c.get("IsFailing") for c in checks):
        return "FAILURE"
    if any(c.get("IsPending") for c in checks):
        return "PENDING"
    return "SUCCESS"


def _fetch_checks_over_rest(
    owner: str,
    repo: str,
    pr_number: int,
    graphql_error: str = "",
) -> dict:
    """Read checks over REST and return the same dict shape as the GraphQL path.

    IsRequired is False on every row here: REST has no such field. The caller
    marks required rows from the branch ruleset once it has fetched it.
    """
    try:
        snapshot = fetch_checks_rest(owner, repo, pr_number)
    except PullRequestNotFoundError:
        return {"Error": "NotFound", "Message": f"PR #{pr_number} not found in {owner}/{repo}"}
    except RuntimeError as exc:
        msg = str(exc)
        prefix = f"GraphQL query failed: {graphql_error}; " if graphql_error else ""
        return {"Error": "ApiError", "Message": f"{prefix}REST fallback failed: {msg}"}

    checks = dedupe_checks([c for c in map(normalize_check, snapshot["Nodes"]) if c])
    return {
        "Number": snapshot["Number"],
        "BaseBranch": snapshot["BaseBranch"],
        "MergeState": snapshot["MergeState"],
        "MergeStateStatus": snapshot["MergeStateStatus"],
        "Checks": checks,
        "AllState": _overall_state(checks),
        # A suite with no run yet is GraphQL's empty present rollup (#2304).
        "HasChecks": bool(checks) or snapshot["HasCheckSuites"],
        "ChecksIncomplete": not snapshot["PagesComplete"],
        "HeadCommittedAt": snapshot["HeadCommittedAt"],
        "DataSource": "rest",
    }


def fetch_checks(
    owner: str,
    repo: str,
    pr_number: int,
    *,
    prefer_rest: bool = False,
) -> dict:
    """Execute the GraphQL query and return the parsed result.

    A rate-limit refusal from GraphQL falls back to REST, which has its own
    quota (issue #6391). ``prefer_rest`` skips GraphQL, so a ``--wait`` loop
    that already fell back does not spend its retry ladder on every poll.
    """
    if prefer_rest:
        return _fetch_checks_over_rest(owner, repo, pr_number)
    try:
        data = gh_graphql(
            _CHECKS_QUERY,
            {"owner": owner, "repo": repo, "number": pr_number},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if is_rate_limit_refusal(msg):
            return _fetch_checks_over_rest(owner, repo, pr_number, graphql_error=msg)
        if is_pr_not_found(msg):
            return {"Error": "NotFound", "Message": f"PR #{pr_number} not found in {owner}/{repo}"}
        return {"Error": "ApiError", "Message": f"GraphQL query failed: {msg}"}

    pr = data.get("repository", {}).get("pullRequest")
    if pr is None:
        return {"Error": "NotFound", "Message": "PR not found in response"}

    mergeable = pr.get("mergeable")
    merge_state_status = pr.get("mergeStateStatus")
    merge_state = "UNKNOWN" if mergeable is None else str(mergeable)

    commits = pr.get("commits", {}).get("nodes", [])
    if not commits:
        return {
            "Number": pr.get("number"),
            "BaseBranch": pr.get("baseRefName"),
            "MergeState": merge_state,
            "MergeStateStatus": merge_state_status,
            "Checks": [],
            "AllState": "UNKNOWN",
            "HasChecks": False,
            "HeadCommittedAt": None,
        }

    commit = commits[0]
    commit_obj = commit.get("commit", {}) or {}
    rollup = commit_obj.get("statusCheckRollup")
    if not rollup:
        return {
            "Number": pr.get("number"),
            "BaseBranch": pr.get("baseRefName"),
            "MergeState": merge_state,
            "MergeStateStatus": merge_state_status,
            "Checks": [],
            "AllState": "UNKNOWN",
            "HasChecks": False,
            "HeadCommittedAt": commit_obj.get("committedDate"),
        }

    all_state = rollup.get("state", "UNKNOWN")
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
        "BaseBranch": pr.get("baseRefName"),
        "MergeState": merge_state,
        "MergeStateStatus": merge_state_status,
        "Checks": checks,
        "AllState": all_state,
        "HasChecks": True,
        "ChecksIncomplete": not pages_complete,
        "HeadCommittedAt": commit_obj.get("committedDate"),
    }


def derive_required_state(
    *,
    has_checks: bool,
    checks_incomplete: bool,
    failed_required: list[str],
    pending_required: list[str],
    missing_required: list[str] | None,
    missing_queued: bool = False,
) -> str:
    """Return the rollup state over required checks only.

    UNKNOWN when no checks reported or pagination did not finish, FAILURE when
    a required check failed or a ruleset context never reported past the grace
    window, PENDING when a required check is still running or a ruleset context
    is only queued (issue #6389), otherwise SUCCESS. Non-required checks never
    move this value. Issue #6396.
    """
    if not has_checks or checks_incomplete:
        return "UNKNOWN"
    if failed_required or (missing_required and not missing_queued):
        return "FAILURE"
    if pending_required or missing_queued:
        return "PENDING"
    return "SUCCESS"


def _rest_unproven_names(
    check_data: dict,
    checks_by_name: dict[str, dict],
    is_required_by_name: dict[str, bool],
) -> set[str]:
    """Return REST row names that are failing or pending but not marked required.

    REST marks required rows from the branch ruleset only. A check that classic
    branch protection requires stays unmarked, so a red or running unmarked row
    cannot be proven non-required. ``build_output`` keeps these rows under
    ``--required-only`` and refuses a green RequiredState while any exist.
    GraphQL carries ``isRequired`` per row, so it never has unproven rows.
    """
    if check_data.get("DataSource") != "rest":
        return set()
    return {
        name
        for name, check in checks_by_name.items()
        if not is_required_by_name.get(name, False)
        and (check.get("IsFailing") or check.get("IsPending"))
    }


def build_output(
    check_data: dict,
    owner: str,
    repo: str,
    required_only: bool = False,
    ruleset_contexts: list[str] | None = None,
    missing_grace_seconds: int = MISSING_GRACE_SECONDS,
) -> dict:
    """Build the final output object from check data.

    Groups checks by name and ORs the required status across all rows
    for each name, matching test_pr_merge_ready.py semantics. Returns
    structured lists of pending and failed required checks.

    If ``ruleset_contexts`` is provided (from the branch ruleset API), computes
    ``MissingRequired``: context names the ruleset requires but that never
    reported any check run. These are invisible to isRequired-based logic.
    Refs issue #4359.
    """
    checks_value = check_data.get("Checks")
    if checks_value is None:
        checks = []
    elif not isinstance(checks_value, list):
        raise ValueError("Checks must be a list")
    else:
        checks = checks_value

    # Group by name and apply OR semantics for isRequired flag.
    checks_by_name, is_required_by_name, _ = group_checks_by_name(checks)

    # Apply required_only filter: keep only checks where any row for that
    # name has isRequired=true.
    rest_unproven = _rest_unproven_names(check_data, checks_by_name, is_required_by_name)
    if required_only:
        checks_by_name = {
            name: check
            for name, check in checks_by_name.items()
            if is_required_by_name.get(name, False) or name in rest_unproven
        }

    # Update each check with the ORed required status.
    for name, check in checks_by_name.items():
        check["IsRequired"] = is_required_by_name.get(name, False)

    filtered_checks = list(checks_by_name.values())

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
    all_passing = (
        has_checks
        and len(filtered_checks) > 0
        and failed_count == 0
        and pending_count == 0
        and not checks_incomplete
        and merge_ref_usable
    )

    # Extract lists of pending and failed required checks for structured
    # output so downstream agents can distinguish the two categories.
    pending_required, failed_required = extract_required_check_lists(
        filtered_checks, is_required_by_name
    )

    # Issue #4359: required checks that never triggered any run are invisible
    # to isRequired-based logic. Cross-reference against the branch ruleset to
    # surface them as a distinct MISSING state.
    reported_names = {c.get("Name", "") for c in checks if c.get("IsRequired")}
    missing_required: list[str] | None
    if ruleset_contexts is not None:
        missing_required = find_missing_required(ruleset_contexts, reported_names)
    else:
        missing_required = None
    all_passing = all_passing and not missing_required
    # Issue #6389: an aggregate required check is created only after its split
    # jobs finish, so inside the grace window after the head commit an absent
    # check is queued, not stranded. Unknown head age stays "absent".
    missing_queued = bool(missing_required) and missing_checks_queued(
        check_data.get("HeadCommittedAt"), missing_grace_seconds
    )
    required_state = derive_required_state(
        has_checks=has_checks,
        checks_incomplete=checks_incomplete,
        failed_required=failed_required,
        pending_required=pending_required,
        missing_required=missing_required,
        missing_queued=missing_queued,
    )
    # REST has no per-row isRequired flag. Without a ruleset listing required
    # checks, no row is marked required, so a green required set is not proven.
    # With one, a failing or pending row outside it may still be required by
    # classic branch protection, which the ruleset lookup cannot see.
    rest_unproven_required = check_data.get("DataSource") == "rest" and (
        not ruleset_contexts or bool(rest_unproven)
    )
    if rest_unproven_required and required_state == "SUCCESS":
        required_state = "UNKNOWN"

    return {
        "Success": True,
        "Number": check_data.get("Number"),
        "Owner": owner,
        "Repo": repo,
        "BaseBranch": check_data.get("BaseBranch"),
        # GitHub's rollup over every check, required or not. A red non-required
        # check makes this FAILURE while the PR stays mergeable. Use
        # RequiredState to decide whether a required gate blocks.
        "AllState": check_data.get("AllState", "UNKNOWN"),
        "RequiredState": required_state,
        "MergeState": merge_state,
        "MergeStateStatus": merge_state_status,
        "MergeRefUsable": merge_ref_usable,
        "MergeStateWarning": merge_state_warning,
        "HasChecks": has_checks,
        # Which transport answered. "rest" means GraphQL was rate limited and
        # IsRequired came from the branch ruleset, not from isRequired.
        "DataSource": check_data.get("DataSource", "graphql"),
        "Checks": [
            {
                "Name": c["Name"],
                "State": c["State"],
                "Conclusion": c["Conclusion"],
                "DetailsUrl": c["DetailsUrl"],
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
        # Issue #4359: required checks from the branch ruleset that produced no
        # check run at all. None when the ruleset fetch was skipped or failed
        # (caller should treat as unknown, not empty).
        "MissingRequiredChecks": missing_required,
        # Issue #6389: True when every missing check is still inside the grace
        # window after the head commit, so it may be queued rather than absent.
        "MissingRequiredQueued": missing_queued,
        "HeadCommittedAt": check_data.get("HeadCommittedAt"),
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
        "--pull-request",
        type=int,
        required=True,
        help="PR number",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until all checks complete or timeout",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Maximum wait time in seconds (default: 300). Keep --wait at or "
        f"below {MAX_WAIT_TIMEOUT_SECONDS}: the agent tool call is killed at 600 seconds "
        "and returns no result.",
    )
    parser.add_argument(
        "--missing-grace-seconds",
        type=int,
        default=MISSING_GRACE_SECONDS,
        help="Seconds after the head commit during which a required check absent "
        "from the rollup counts as queued, and --wait keeps polling for it "
        f"(default: {MISSING_GRACE_SECONDS}). 0 reports absent checks as never reported at once.",
    )
    parser.add_argument(
        "--required-only",
        action="store_true",
        help="Filter output to required checks only",
    )
    parser.add_argument(
        "--base-branch",
        default=None,
        help="Base branch to read the ruleset from for missing-check detection "
        "(default: PR base branch). Pass empty string to skip ruleset fetch.",
    )
    add_output_format_arg(parser)
    return parser


def _missing_names(missing: list[str]) -> str:
    """Return the MISSING name list, truncated to three names."""
    return f"MISSING: {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''}"


def _resolve_status(
    output: dict,
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
    missing = output.get("MissingRequiredChecks")
    queued = bool(output.get("MissingRequiredQueued"))
    if missing and not queued:
        return (
            f"PR #{number}: {len(missing)} required check(s) never reported "
            f"({_missing_names(missing)}). "
            f"{_MISSING_RECOVERY_HINT}",
            "FAIL",
        )
    if output["FailedCount"] > 0:
        return f"PR #{number}: {output['FailedCount']} check(s) failed", "FAIL"
    if missing:
        wait_note = f" after {timeout_seconds} seconds" if timed_out_pending else ""
        return (
            f"PR #{number}: {len(missing)} required check(s) not yet reported{wait_note} "
            f"({_missing_names(missing)}). The head commit is inside the grace window, "
            "so they may still be queued. Do not close and reopen the PR yet.",
            "WARNING",
        )
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


def failure_data(
    number: int | None,
    owner: str | None = None,
    repo: str | None = None,
    base_branch: str | None = None,
) -> dict:
    """Return the Data object for a failure envelope.

    Every key of a successful run is present. Values the failure left unknown
    are None, never absent, and AllPassing is False so a caller that skips the
    Success check still fails closed.
    """
    data: dict = dict.fromkeys(_DATA_KEYS)
    data.update(
        Success=False,
        Number=number,
        Owner=owner,
        Repo=repo,
        BaseBranch=base_branch,
        AllPassing=False,
    )
    return data


def _emit_failure(
    message: str,
    code: int,
    error_type: str,
    fmt: str,
    data: dict,
) -> None:
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=fmt,
        script_name="get_pr_checks.py",
        extra=data,
    )


def _handle_fetch_error(
    check_data: dict,
    pr_number: int,
    fmt: object,
    owner: str | None = None,
    repo: str | None = None,
) -> int | None:
    """Return an exit code if check_data carries an error, else None."""
    codes = {"NotFound": 2, "ApiError": 3}
    error = check_data.get("Error")
    if error not in codes:
        return None
    _emit_failure(
        check_data["Message"],
        codes[error],
        error,
        fmt,
        failure_data(pr_number, owner, repo),
    )
    return codes[error]


def _resolve_repo_or_fail(args: argparse.Namespace, fmt: str) -> tuple[str, str]:
    """Authenticate and resolve owner and repo, keeping json stdout parseable.

    The helpers behind this call write to stderr and raise SystemExit. In json
    mode that left stdout empty, so a piped caller got a parse error instead of
    the failure. Emit one error envelope, keep the stderr text, and re-raise
    with the original exit code.
    """
    captured = io.StringIO()
    try:
        with contextlib.redirect_stderr(captured):
            assert_gh_authenticated()
            resolved = resolve_repo_params(args.owner, args.repo)
    except SystemExit as exc:
        sys.stderr.write(captured.getvalue())
        code = exc.code if isinstance(exc.code, int) and not isinstance(exc.code, bool) else 1
        if fmt == "json":
            _emit_failure(
                captured.getvalue().strip() or f"Preflight failed with exit code {code}",
                code,
                _PREFLIGHT_ERROR_TYPES.get(code, "General"),
                fmt,
                failure_data(args.pull_request, args.owner or None, args.repo or None),
            )
        raise
    sys.stderr.write(captured.getvalue())
    return resolved.owner, resolved.repo


def _mark_rest_required(
    check_data: dict,
    ruleset_contexts: list[str] | None,
    required_only: bool,
    pr_number: int,
    fmt: object,
    owner: str | None = None,
    repo: str | None = None,
) -> int | None:
    """Mark required rows on REST data from the ruleset, or return exit code 3.

    REST has no per-row required flag. When the ruleset cannot be read (``None``)
    or lists no required checks (``[]``, which is what a branch with only classic
    branch protection, or none, returns), ``--required-only`` would silently drop
    every row, so it fails instead of reporting an empty pass. Without
    ``--required-only`` the rows stay unmarked, the caller still sees every
    failing check, and ``build_output`` reports RequiredState as UNKNOWN.
    """
    if check_data.get("DataSource") != "rest":
        return None
    if ruleset_contexts is not None:
        mark_required_from_ruleset(check_data["Checks"], ruleset_contexts)
    if ruleset_contexts or not required_only:
        return None
    _emit_failure(
        "GraphQL is rate limited and REST cannot tell which checks are required: "
        "the branch ruleset was not read or lists no required checks; "
        "rerun without --required-only",
        3,
        "ApiError",
        fmt,
        failure_data(pr_number, owner, repo, check_data.get("BaseBranch")),
    )
    return 3


def _downgrade_required_state(output: dict, checks_incomplete: bool) -> None:
    """Report a green RequiredState as UNKNOWN when polling found the set incomplete.

    ``main`` learns the check set is incomplete after ``build_output`` ran, so
    a green required set is not proven.
    """
    if checks_incomplete and output["RequiredState"] == "SUCCESS":
        output["RequiredState"] = "UNKNOWN"


def _warn_if_wait_exceeds_tool_cap(wait: bool, timeout_seconds: int) -> None:
    """Warn on stderr when a --wait budget would outlive the 600 second tool cap."""
    if wait and timeout_seconds > MAX_WAIT_TIMEOUT_SECONDS:
        print(
            f"Warning: --timeout-seconds {timeout_seconds} exceeds "
            f"{MAX_WAIT_TIMEOUT_SECONDS}; a 600 second tool call is killed with no result. "
            "Re-run --wait instead.",
            file=sys.stderr,
        )


def _holds_wait_for_queued(output: dict) -> bool:
    """Return True when --wait should keep polling for queued required checks."""
    return bool(output.get("MissingRequiredQueued")) and output["FailedCount"] == 0


def _exit_code(output: dict, checks_incomplete: bool, timed_out_pending: bool) -> int:
    """Return the exit code derived from the final output dict."""
    if checks_incomplete or timed_out_pending:
        return 7
    if output["FailedCount"] > 0:
        return 1
    if output.get("MissingRequiredChecks"):
        return 1
    if not output.get("MergeRefUsable", True):
        return 1
    return 0


def _load_ruleset(
    owner: str,
    repo: str,
    check_data: dict,
    args: argparse.Namespace,
    fmt: object,
) -> tuple[list[str] | None, int | None]:
    """Fetch the base branch ruleset once, before polling.

    Issue #4359: a stable snapshot keeps missing-check detection relevant.
    Returns (contexts, exit_code). ``contexts`` is None when the fetch was
    skipped (empty base branch) or failed; a failure also sets exit code 3.
    """
    base_branch = (
        args.base_branch.strip()
        if args.base_branch is not None
        else str(check_data.get("BaseBranch") or "")
    )
    if not base_branch:
        return None, None
    ruleset_contexts = fetch_ruleset_required_contexts(owner, repo, base_branch)
    if ruleset_contexts is not None:
        return ruleset_contexts, None
    _emit_failure(
        f"Failed to read required checks for base branch {base_branch!r}",
        3,
        "ApiError",
        fmt,
        failure_data(args.pull_request, owner, repo, base_branch),
    )
    return None, 3


def _poll_checks(
    owner: str,
    repo: str,
    previous: dict,
    ruleset_contexts: list[str] | None,
    args: argparse.Namespace,
    fmt: object,
) -> tuple[dict, int | None]:
    """Sleep, refetch the checks, and return (check_data, exit_code).

    Once GraphQL has been rate limited, stay on REST: each GraphQL poll would
    spend its retry ladder (up to 45s) on the same refusal (issue #6391).
    """
    time.sleep(10)
    check_data = fetch_checks(
        owner,
        repo,
        args.pull_request,
        prefer_rest=previous.get("DataSource") == "rest",
    )
    rc = _handle_fetch_error(check_data, args.pull_request, fmt, owner, repo)
    if rc is None:
        rc = _mark_rest_required(
            check_data, ruleset_contexts, args.required_only, args.pull_request, fmt, owner, repo
        )
    return check_data, rc


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    owner, repo = _resolve_repo_or_fail(args, fmt)

    check_data = fetch_checks(owner, repo, args.pull_request)
    rc = _handle_fetch_error(check_data, args.pull_request, fmt, owner, repo)
    if rc is not None:
        return rc

    ruleset_contexts, rc = _load_ruleset(owner, repo, check_data, args, fmt)
    if rc is None:
        rc = _mark_rest_required(
            check_data, ruleset_contexts, args.required_only, args.pull_request, fmt, owner, repo
        )
    if rc is not None:
        return rc

    _warn_if_wait_exceeds_tool_cap(args.wait, args.timeout_seconds)

    start_time = time.monotonic()
    max_iterations = math.ceil(args.timeout_seconds / 10)
    iteration = 0
    settled = False
    checks_incomplete = False

    while True:
        iteration += 1

        output = build_output(
            check_data,
            owner,
            repo,
            args.required_only,
            ruleset_contexts,
            args.missing_grace_seconds,
        )
        checks_incomplete = checks_incomplete or bool(output.get("ChecksIncomplete", False))

        # Under --wait, an empty present rollup is usually a transient GraphQL
        # race, not "no checks configured". Keep polling only when GitHub
        # returned a rollup object with no contexts; a missing rollup is a real
        # no-checks PR and must settle immediately. See #2304.
        empty_present_rollup = output["HasChecks"] and not output["Checks"]
        waiting_on_empty = args.wait and empty_present_rollup

        # Issue #6389: a queued required check has no row to count as pending.
        # Hold the wait for it unless a check already failed, which makes the
        # PR red whatever the queued check reports.
        waiting_on_queued = args.wait and _holds_wait_for_queued(output)

        # Done when not waiting, or settled: nothing pending, nothing queued,
        # and not an empty rollup we are still waiting on.
        if not args.wait or (
            output["PendingCount"] == 0 and not waiting_on_empty and not waiting_on_queued
        ):
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

        check_data, rc = _poll_checks(owner, repo, check_data, ruleset_contexts, args, fmt)
        if rc is not None:
            return rc

    output["ChecksIncomplete"] = checks_incomplete
    _downgrade_required_state(output, checks_incomplete)
    timed_out_pending = not settled and (
        output["PendingCount"] > 0 or _holds_wait_for_queued(output)
    )

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


if __name__ == "__main__":
    raise SystemExit(main())
