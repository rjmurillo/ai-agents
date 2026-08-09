#!/usr/bin/env python3
"""Diagnose why a PR reports mergeStateStatus BLOCKED.

Cross-references the base branch ruleset required checks against the PR's
statusCheckRollup and unresolved review threads to produce a discriminated
cause list:

  MISSING  - required by the ruleset, never ran (produced no row in the rollup)
  FAILING  - required by the ruleset or isRequired=true, conclusion is failing
  REVIEWS  - an approval is required or changes were requested
  THREADS  - unresolved review threads requiring resolution

When all gates are satisfied, reports "likely mergeable" because BLOCKED is not
authoritative: PRs with all gates satisfied have been observed to merge on the
first attempt.

Exit codes:
    0 - No identified gate blocks the merge
    1 - A required gate blocks the merge
    2 - Required checks are still pending, or the PR was not found
    3 - API error
    4 - Auth error
"""

from __future__ import annotations

import os
import sys

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
    sys.exit(2)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

import argparse
import subprocess
from typing import Any

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
)
from github_core.checks_rollup import extract_workflow_run_number, partition_rows_by_run
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)
from github_core.review_threads import count_unresolved_threads

_SCRIPT_NAME = "why_pr_blocked.py"

# Passing conclusions: SKIPPED satisfies a required context per field data.
_PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
_FAILING_CONCLUSIONS = {
    "FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED",
    "STALE", "STARTUP_FAILURE",
}
_PENDING_STATUSES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}
_BLOCKING_MERGE_STATES = {"CONFLICTING", "UNKNOWN"}
_BLOCKING_MERGE_STATE_STATUSES = {"DIRTY", "UNKNOWN"}

_PR_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            state
            baseRefName
            mergeable
            mergeStateStatus
            reviewDecision
            commits(last: 1) {
                nodes {
                    commit {
                        oid
                        statusCheckRollup {
                            contexts(first: 100) {
                                pageInfo { hasNextPage endCursor }
                                nodes {
                                    ... on CheckRun {
                                        __typename name status conclusion detailsUrl
                                        checkSuite { app { databaseId } }
                                        isRequired(pullRequestNumber: $number)
                                    }
                                    ... on StatusContext {
                                        __typename context state targetUrl
                                        isRequired(pullRequestNumber: $number)
                                    }
                                }
                            }
                        }
                    }
                }
            }
            reviewThreads(first: 100) {
                pageInfo { hasNextPage endCursor }
                nodes { isResolved }
            }
        }
    }
}"""

_CONTEXTS_PAGE_QUERY = """\
query($owner: String!, $repo: String!, $oid: GitObjectID!, $number: Int!, $cursor: String!) {
    repository(owner: $owner, name: $repo) {
        object(oid: $oid) {
            ... on Commit {
                statusCheckRollup {
                    contexts(first: 100, after: $cursor) {
                        pageInfo { hasNextPage endCursor }
                        nodes {
                            ... on CheckRun {
                                __typename name status conclusion detailsUrl
                                checkSuite { app { databaseId } }
                                isRequired(pullRequestNumber: $number)
                            }
                            ... on StatusContext {
                                __typename context state targetUrl
                                isRequired(pullRequestNumber: $number)
                            }
                        }
                    }
                }
            }
        }
    }
}"""

_REVIEW_THREADS_PAGE_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!, $cursor: String!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            reviewThreads(first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes { isResolved }
            }
        }
    }
}"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Diagnose why a PR is blocked.")
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--pull-request", type=int, required=True)
    add_output_format_arg(p)
    return p


def _fetch_ruleset_contexts(
    owner: str,
    repo: str,
    base_branch: str,
) -> list[dict[str, Any]]:
    """Return required context and integration identities."""
    import json as _json

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
        items = _json.loads(raw)
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
    except (TypeError, ValueError, _json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Required-check ruleset response was invalid: {exc}"
        ) from exc


def _normalize_check(node: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a GraphQL context node to a normalized dict."""
    typename = node.get("__typename")
    if typename == "CheckRun":
        status = node.get("status", "")
        conclusion = node.get("conclusion") or ""
        is_pending = status in _PENDING_STATUSES
        is_passing = conclusion in _PASSING_CONCLUSIONS
        is_failing = conclusion in _FAILING_CONCLUSIONS
        return {
            "Name": node.get("name", ""),
            "Type": "CheckRun",
            "State": status,
            "Conclusion": conclusion,
            "DetailsUrl": node.get("detailsUrl", ""),
            "IntegrationId": (
                ((node.get("checkSuite") or {}).get("app") or {}).get("databaseId")
            ),
            "IsRequired": bool(node.get("isRequired", False)),
            "IsPending": is_pending,
            "IsPassing": is_passing,
            "IsFailing": is_failing,
        }
    if typename == "StatusContext":
        state = node.get("state", "")
        return {
            "Name": node.get("context", ""),
            "Type": "StatusContext",
            "State": state,
            "Conclusion": state,
            "DetailsUrl": node.get("targetUrl", ""),
            "IntegrationId": None,
            "IsRequired": bool(node.get("isRequired", False)),
            "IsPending": state in ("PENDING", "EXPECTED"),
            "IsPassing": state == "SUCCESS",
            "IsFailing": state in ("FAILURE", "ERROR"),
        }
    return None


def _check_rank(check: dict[str, Any]) -> int:
    if check.get("IsPassing"):
        return 0
    if check.get("IsFailing"):
        return 1
    if check.get("IsPending"):
        return 2
    return 3


_TYPE_RANK = {"CheckRun": 0, "StatusContext": 1}


def _dedupe_rank(check: dict[str, Any]) -> tuple[int, int]:
    """Rank by source type first, then verdict precedence."""
    check_type = str(check.get("Type") or "")
    return (_TYPE_RANK.get(check_type, 2), _check_rank(check))


def _check_workflow_run_number(check: dict[str, Any]) -> int | None:
    """Return the workflow run id exposed by a CheckRun details URL."""
    if check.get("Type") != "CheckRun":
        return None
    details_url = check.get("DetailsUrl")
    run_number = extract_workflow_run_number(
        details_url if isinstance(details_url, str) else None
    )
    return run_number if isinstance(run_number, int) else None


def _collapse_same_run_siblings(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep a failing same-name sibling when both ran in one workflow run."""
    representatives: list[dict[str, Any]] = []
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


def _select_cross_run_winner(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Select the latest workflow run when every CheckRun exposes its id."""
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
            check
            for check, run_number in check_run_pairs
            if run_number == latest_run
        ]
        return sorted(latest_candidates, key=_dedupe_rank)[0]
    return sorted(candidates, key=_dedupe_rank)[0]


def _dedupe_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicate check rows before grouping by name."""
    integration_ids_by_name: dict[str, set[int]] = {}
    for check in checks:
        integration_id = check.get("IntegrationId")
        if integration_id is not None:
            name = str(check.get("Name") or "")
            integration_ids_by_name.setdefault(name, set()).add(integration_id)

    rows_by_identity: dict[tuple[str, int | None], list[dict[str, Any]]] = {}
    required_by_identity: dict[tuple[str, int | None], bool] = {}
    order: list[tuple[str, int | None]] = []

    for check in checks:
        name_value = check.get("Name")
        name = "" if name_value is None else str(name_value)
        integration_id = check.get("IntegrationId")
        known_ids = integration_ids_by_name.get(name, set())
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
        winner = _select_cross_run_winner(candidates)
        deduped.append(
            {**winner, "IsRequired": required_by_identity[identity]}
        )
    return deduped


def _fetch_context_page(
    owner: str, repo: str, pr_number: int, oid: str, cursor: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = gh_graphql(
        _CONTEXTS_PAGE_QUERY,
        {"owner": owner, "repo": repo, "oid": oid, "number": pr_number, "cursor": cursor},
    )
    commit_obj = (data.get("repository") or {}).get("object") or {}
    rollup = commit_obj.get("statusCheckRollup") or {}
    contexts_obj = rollup.get("contexts") or {}
    return list(contexts_obj.get("nodes") or []), contexts_obj.get("pageInfo") or {}


def _fetch_review_thread_page(
    owner: str, repo: str, pr_number: int, cursor: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = gh_graphql(
        _REVIEW_THREADS_PAGE_QUERY,
        {"owner": owner, "repo": repo, "number": pr_number, "cursor": cursor},
    )
    pr = (data.get("repository") or {}).get("pullRequest") or {}
    review_threads = pr.get("reviewThreads") or {}
    return list(review_threads.get("nodes") or []), review_threads.get("pageInfo") or {}


def diagnose(
    owner: str,
    repo: str,
    pr_number: int,
) -> dict[str, Any]:
    """Run the full blocked diagnostic for one PR. Returns the result dict."""
    try:
        data = gh_graphql(_PR_QUERY, {"owner": owner, "repo": repo, "number": pr_number})
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg or "not found" in msg:
            return {"Error": "NotFound", "Message": f"PR #{pr_number} not found"}
        return {"Error": "ApiError", "Message": f"GraphQL query failed: {msg}"}

    pr = (data.get("repository") or {}).get("pullRequest")
    if pr is None:
        return {"Error": "NotFound", "Message": f"PR #{pr_number} not found in response"}

    base_branch = pr.get("baseRefName", "")
    mergeable = pr.get("mergeable") or "UNKNOWN"
    merge_state_status = pr.get("mergeStateStatus", "")
    review_decision = pr.get("reviewDecision") or ""

    # Collect raw check nodes from rollup.
    commits = (pr.get("commits") or {}).get("nodes") or []
    raw_nodes: list[dict[str, Any]] = []
    if commits:
        commit_obj = (commits[0].get("commit") or {})
        rollup = commit_obj.get("statusCheckRollup")
        if rollup:
            contexts_obj = rollup.get("contexts") or {}
            raw_nodes = list(contexts_obj.get("nodes") or [])
            page_info = contexts_obj.get("pageInfo") or {}
            cursor = page_info.get("endCursor")
            oid = commit_obj.get("oid") or ""
            while page_info.get("hasNextPage") and cursor and oid:
                page_nodes, page_info = _fetch_context_page(
                    owner, repo, pr_number, oid, cursor
                )
                raw_nodes.extend(page_nodes)
                cursor = page_info.get("endCursor")

    checks = _dedupe_checks([
        n for node in raw_nodes if (n := _normalize_check(node)) is not None
    ])

    # Ruleset required contexts (ground truth independent of what reported).
    try:
        ruleset_required = (
            _fetch_ruleset_contexts(owner, repo, base_branch)
            if base_branch
            else []
        )
    except RuntimeError as exc:
        return {
            "Error": "ApiError",
            "Message": f"Required-check inventory failed: {exc}",
        }

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

    missing: list[str] = sorted({
        str(requirement["Context"])
        for requirement in ruleset_required
        if not any(
            matches_requirement(check, requirement)
            for check in checks
        )
    })

    required_checks = [
        check for check in checks
        if check.get("IsRequired")
        or any(
            matches_requirement(check, requirement)
            for requirement in ruleset_required
        )
    ]
    failing: list[str] = sorted({
        str(check.get("Name", ""))
        for check in required_checks
        if check.get("IsFailing")
    })
    pending_required: list[str] = sorted({
        str(check.get("Name", ""))
        for check in required_checks
        if check.get("IsPending")
    })

    # Unresolved review threads.
    review_threads = pr.get("reviewThreads") or {}
    thread_nodes = list(review_threads.get("nodes") or [])
    page_info = review_threads.get("pageInfo") or {}
    cursor = page_info.get("endCursor")
    while page_info.get("hasNextPage") and cursor:
        page_nodes, page_info = _fetch_review_thread_page(owner, repo, pr_number, cursor)
        thread_nodes.extend(page_nodes)
        cursor = page_info.get("endCursor")
    unresolved_threads = count_unresolved_threads(thread_nodes)

    causes: list[str] = []
    if mergeable == "CONFLICTING" or merge_state_status == "DIRTY":
        causes.append("MERGE (conflicts)")
    elif (
        mergeable in _BLOCKING_MERGE_STATES
        or merge_state_status in _BLOCKING_MERGE_STATE_STATUSES
    ):
        causes.append("MERGE (state unknown)")
    if missing:
        causes.append(f"MISSING ({len(missing)} required check(s) never reported)")
    if failing:
        causes.append(f"FAILING ({len(failing)} required check(s))")
    if pending_required:
        causes.append(f"PENDING ({len(pending_required)} required check(s))")
    if review_decision == "CHANGES_REQUESTED":
        causes.append("REVIEWS (changes requested)")
    elif review_decision == "REVIEW_REQUIRED":
        causes.append("REVIEWS (approval required)")
    if unresolved_threads:
        causes.append(f"THREADS ({unresolved_threads} unresolved review thread(s))")

    likely_mergeable = not causes

    return {
        "Success": True,
        "Number": pr_number,
        "Owner": owner,
        "Repo": repo,
        "BaseBranch": base_branch,
        "Mergeable": mergeable,
        "MergeStateStatus": merge_state_status,
        "ReviewDecision": review_decision,
        "LikelyMergeable": likely_mergeable,
        "Causes": causes,
        "MissingRequiredChecks": missing,
        "FailingRequiredChecks": failing,
        "PendingRequiredChecks": pending_required,
        "UnresolvedThreads": unresolved_threads,
        "RulesetRequiredContexts": [
            requirement["Context"] for requirement in ruleset_required
        ],
        "RulesetRequiredChecks": ruleset_required,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    result = diagnose(owner, repo, args.pull_request)

    if result.get("Error") == "NotFound":
        write_skill_error(
            result["Message"], 2, error_type="NotFound",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 2

    if result.get("Error") == "ApiError":
        write_skill_error(
            result["Message"], 3, error_type="ApiError",
            output_format=fmt, script_name=_SCRIPT_NAME,
        )
        return 3

    causes = result.get("Causes") or []
    if result.get("LikelyMergeable"):
        summary = f"PR #{args.pull_request}: likely mergeable (no blocking causes found)"
        status = "PASS"
    else:
        summary = f"PR #{args.pull_request} BLOCKED: {'; '.join(causes)}"
        status = "FAIL"

    write_skill_output(
        result,
        output_format=fmt,
        human_summary=summary,
        status=status,
        script_name=_SCRIPT_NAME,
    )
    hard_blocker = bool(
        result.get("MissingRequiredChecks")
        or result.get("FailingRequiredChecks")
        or result.get("UnresolvedThreads")
        or result.get("ReviewDecision") in {"CHANGES_REQUESTED", "REVIEW_REQUIRED"}
        or result.get("Mergeable") == "CONFLICTING"
        or result.get("MergeStateStatus") == "DIRTY"
    )
    if hard_blocker:
        return 1
    if result.get("PendingRequiredChecks"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
