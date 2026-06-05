#!/usr/bin/env python3
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
import math
import os
import sys
import time

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
    gh_graphql,
    resolve_repo_params,
)
from github_core.checks_rollup import (  # noqa: E402
    extract_required_check_lists,
    group_checks_by_name,
)
from github_core.output import (  # noqa: E402
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
# Check normalization
# ---------------------------------------------------------------------------


def normalize_check(ctx: dict) -> dict | None:
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
# This script leaves OverallState as GitHub's rollup value. Deduplication only
# affects the per-check rows and derived counts, such as FailedCount. The
# precedence follows test_pr_merge_ready.py verdict ordering: OK > FAIL >
# PENDING. A passing entry from a re-run supersedes a prior failure ("OK if any
# SUCCESS exists" per the PR #1887 retrospective). A failure still wins over a
# pending retry when no passing run exists, so pending work does not hide the
# last concrete failure. Any pending signal is still retained for wait polling,
# including when a same-name passing run is present.
#
# Stricter/looser/different than canonical: test_pr_merge_ready.py treats a
# CANCELLED-only group as no-opinion (SKIP) so it neither blocks nor counts as
# passed. Here, normalize_check already maps CANCELLED into IsFailing (it is in
# _FAILING_CONCLUSIONS), so a CANCELLED-only group surfaces as a failing check.
# That preserves this script's long-standing CANCELLED semantics; the dedupe
# only collapses duplicate names and prefers a passing run when one exists for
# the same name.

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


def dedupe_checks(checks: list[dict]) -> list[dict]:
    """Collapse multiple runs of one check name to the winning entry.

    Groups by ``Name`` and keeps the entry with the best precedence
    (passing over failing over pending), so a re-run SUCCESS supersedes a
    stale FAILURE on the same commit. The first-seen order of surviving
    names is preserved. CheckRun rows win over StatusContext rows with the
    same name. Required-check status is retained when any duplicate row for a
    name is required.
    """
    best_by_name: dict[str, dict] = {}
    required_by_name: dict[str, bool] = {}
    pending_by_name: dict[str, bool] = {}
    order: list[str] = []
    for check in checks:
        name_value = check.get("Name")
        name = "" if name_value is None else name_value
        required_by_name[name] = required_by_name.get(name, False) or bool(
            check.get("IsRequired")
        )
        pending_by_name[name] = pending_by_name.get(name, False) or bool(
            check.get("IsPending")
        )
        current = best_by_name.get(name)
        if current is None:
            best_by_name[name] = check
            order.append(name)
        elif _dedupe_rank(check) < _dedupe_rank(current):
            best_by_name[name] = check

    deduped = []
    for name in order:
        winner = {**best_by_name[name], "IsRequired": required_by_name[name]}
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


def fetch_checks(
    owner: str, repo: str, pr_number: int,
) -> dict:
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

    commits = pr.get("commits", {}).get("nodes", [])
    if not commits:
        return {
            "Number": pr.get("number"),
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
        "Checks": checks,
        "OverallState": overall_state,
        "HasChecks": True,
        "ChecksIncomplete": not pages_complete,
    }


def build_output(
    check_data: dict,
    owner: str,
    repo: str,
    required_only: bool = False,
) -> dict:
    """Build the final output object from check data.

    Groups checks by name and ORs the required status across all rows
    for each name, matching test_pr_merge_ready.py semantics. Returns
    structured lists of pending and failed required checks.
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
    if required_only:
        checks_by_name = {
            name: check for name, check in checks_by_name.items()
            if is_required_by_name.get(name, False)
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
    all_passing = (
        has_checks
        and len(filtered_checks) > 0
        and failed_count == 0
        and pending_count == 0
        and not checks_incomplete
    )

    # Extract lists of pending and failed required checks for structured
    # output so downstream agents can distinguish the two categories.
    pending_required, failed_required = extract_required_check_lists(
        filtered_checks, is_required_by_name
    )

    return {
        "Success": True,
        "Number": check_data.get("Number"),
        "Owner": owner,
        "Repo": repo,
        "OverallState": check_data.get("OverallState", "UNKNOWN"),
        "HasChecks": has_checks,
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
    output: dict,
    timeout_seconds: int,
    timed_out_pending: bool,
    checks_incomplete: bool,
) -> tuple[str, str]:
    """Return (human_summary, status) for the final check output."""
    number = output["Number"]
    if checks_incomplete:
        return (
            f"PR #{number}: checks still unavailable after {timeout_seconds}s "
            "(empty rollup; not treated as passing)",
            "WARNING",
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

    while True:
        iteration += 1
        check_data = fetch_checks(owner, repo, args.pull_request)

        # Handle errors
        if check_data.get("Error") == "NotFound":
            write_skill_error(
                check_data["Message"],
                2,
                error_type="NotFound",
                output_format=fmt,
                script_name="get_pr_checks.py",
                extra={"Number": args.pull_request},
            )
            return 2

        if check_data.get("Error") == "ApiError":
            write_skill_error(
                check_data["Message"],
                3,
                error_type="ApiError",
                output_format=fmt,
                script_name="get_pr_checks.py",
                extra={"Number": args.pull_request},
            )
            return 3

        output = build_output(check_data, owner, repo, args.required_only)
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

    if output["FailedCount"] > 0:
        return 1
    if checks_incomplete or timed_out_pending:
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
