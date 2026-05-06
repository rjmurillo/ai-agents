#!/usr/bin/env python3
"""Check if a PR is ready to merge.

Performs comprehensive merge readiness check:
- Verifies all review threads are resolved
- Checks CI status (required checks passing by default)
- Validates PR state (open, not draft)
- Checks for merge conflicts

By default, only REQUIRED checks block merge. Non-required failing checks
are reported but do not affect CanMerge unless --include-non-required is set.

Multiple rows for the same check name (debounce supersession: a CANCELLED
run plus a later SUCCESS run) are deduplicated by name. The verdict per
name is FAIL if any conclusion is a real failure; OK if any conclusion is
SUCCESS / NEUTRAL / SKIPPED; PENDING if any status is IN_PROGRESS / PENDING.
A name whose only conclusion is CANCELLED carries no opinion and does not
block. The PR #1887 retrospective records four false-FAIL reports caused
by counting CANCELLED debounce rows as failed required checks.

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
import os
import sys
from collections import defaultdict

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
    error_and_exit,
    gh_graphql,
    resolve_repo_params,
)

# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------

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
                        statusCheckRollup {
                            state
                            contexts(first: 100) {
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
      1. FAIL  - any row has a real failure conclusion (not in the passing
                 or no-opinion sets, e.g. FAILURE, TIMED_OUT, ACTION_REQUIRED).
      2. PENDING - any row has status != COMPLETED.
      3. OK    - any row has a passing conclusion.
      4. SKIP  - all rows are CANCELLED (no real opinion); not blocking.

    Aligns with the brief in the PR #1887 retrospective: "OK if any SUCCESS
    exists and no FAILURE; FAIL if any FAILURE; PENDING if any IN_PROGRESS."
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

    if has_failure:
        return "FAIL"
    if has_passing:
        return "OK"
    if has_pending:
        return "PENDING"
    return "SKIP"


def _status_context_verdict(rows: list[dict]) -> str:
    """Reduce multiple StatusContext rows for one name to a single verdict.

    StatusContext does not surface CANCELLED; the typical states are SUCCESS,
    EXPECTED, PENDING, FAILURE, ERROR. We apply the same precedence as the
    CheckRun verdict so callers can treat the two row types uniformly.
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

    if has_failure:
        return "FAIL"
    if has_passing:
        return "OK"
    if has_pending:
        return "PENDING"
    return "SKIP"


def _classify_check_contexts(
    contexts: list[dict],
    *,
    failed_required: list[str],
    pending_required: list[str],
    failed_non_required: list[str],
    pending_non_required: list[str],
) -> None:
    """Group rollup contexts by name and append blocking names to the lists.

    Multiple rows under the same name (debounce supersession) are collapsed
    via _check_run_verdict / _status_context_verdict before being routed to
    the failed/pending buckets. A name whose verdict is OK or SKIP appends
    to nothing; the caller computes passed_checks from the surviving names.

    The is_required flag is taken from any row that carries it; if the rows
    disagree, we OR them (treating the name as required if any row says so),
    because the rollup may produce both a CheckRun and a StatusContext for
    the same logical check and the required flag may live on only one.
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
            is_required_by_name.get(name, False) or bool(ctx.get("isRequired", False))
        )

    for name, rows in grouped_check_runs.items():
        verdict = _check_run_verdict(rows)
        is_required = is_required_by_name.get(name, False)
        _route_verdict(
            name,
            verdict,
            is_required,
            failed_required,
            pending_required,
            failed_non_required,
            pending_non_required,
        )

    for name, rows in grouped_status_contexts.items():
        if name in grouped_check_runs:
            # Already classified via CheckRun; the StatusContext mirror would
            # otherwise double-count. The rollup may publish both for the
            # same logical check.
            continue
        verdict = _status_context_verdict(rows)
        is_required = is_required_by_name.get(name, False)
        _route_verdict(
            name,
            verdict,
            is_required,
            failed_required,
            pending_required,
            failed_non_required,
            pending_non_required,
        )


def _route_verdict(
    name: str,
    verdict: str,
    is_required: bool,
    failed_required: list[str],
    pending_required: list[str],
    failed_non_required: list[str],
    pending_non_required: list[str],
) -> None:
    """Append name to the appropriate bucket given its verdict and required flag."""
    if verdict == "FAIL":
        (failed_required if is_required else failed_non_required).append(name)
    elif verdict == "PENDING":
        (pending_required if is_required else pending_non_required).append(name)


def _count_passed_checks(contexts: list[dict], blocked: list[str]) -> int:
    """Count distinct check names that are not in any blocking bucket.

    Uses the post-dedupe blocked list to compute "everything else passed".
    """
    distinct_names: set[str] = set()
    for ctx in contexts:
        typename = ctx.get("__typename")
        if typename == "CheckRun":
            distinct_names.add(ctx.get("name", "unknown"))
        elif typename == "StatusContext":
            distinct_names.add(ctx.get("context", "unknown"))
    blocked_set = set(blocked)
    return len(distinct_names - blocked_set)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def check_merge_readiness(
    owner: str,
    repo: str,
    pr_number: int,
    ignore_ci: bool = False,
    ignore_threads: bool = False,
    include_non_required: bool = False,
) -> dict:
    """Check if a PR is ready to merge. Returns result dict."""
    try:
        data = gh_graphql(
            _MERGE_READY_QUERY,
            {"owner": owner, "repo": repo, "number": pr_number},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg:
            error_and_exit(f"PR #{pr_number} not found in {owner}/{repo}", 2)
        error_and_exit(f"Failed to query PR status: {msg}", 3)

    pr = data.get("repository", {}).get("pullRequest")
    if pr is None:
        error_and_exit(f"PR #{pr_number} not found", 2)

    reasons: list[str] = []

    # Check 1: PR State
    if pr["state"] != "OPEN":
        reasons.append(f"PR is {pr['state'].lower()}, not open")
    if pr.get("isDraft"):
        reasons.append("PR is in draft state")

    # Check 2: Merge conflicts
    mergeable = pr.get("mergeable", "")
    if mergeable == "CONFLICTING":
        reasons.append("PR has merge conflicts")
    elif mergeable == "UNKNOWN":
        reasons.append("Merge status is being calculated")

    # Check 3: Review Threads
    unresolved_count = 0
    total_threads = 0
    if not ignore_threads:
        threads = pr.get("reviewThreads", {})
        total_threads = threads.get("totalCount", 0)
        nodes = threads.get("nodes", [])
        unresolved_count = sum(1 for t in nodes if not t.get("isResolved", True))
        if unresolved_count > 0:
            reasons.append(f"{unresolved_count} unresolved review thread(s)")

    # Check 4: CI Status
    failed_required: list[str] = []
    pending_required: list[str] = []
    failed_non_required: list[str] = []
    pending_non_required: list[str] = []
    passed_checks = 0
    ci_passing = True

    if not ignore_ci:
        commits = pr.get("commits", {}).get("nodes", [])
        if commits:
            commit = commits[0]
            rollup = commit.get("commit", {}).get("statusCheckRollup")
            if rollup:
                contexts = rollup.get("contexts", {}).get("nodes", [])
                _classify_check_contexts(
                    contexts,
                    failed_required=failed_required,
                    pending_required=pending_required,
                    failed_non_required=failed_non_required,
                    pending_non_required=pending_non_required,
                )
                passed_checks = _count_passed_checks(
                    contexts,
                    blocked=failed_required + pending_required + failed_non_required + pending_non_required,
                )

        # Always block on required check failures
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

        # Only block on non-required if flag set
        if include_non_required:
            if failed_non_required:
                reasons.append(
                    f"{len(failed_non_required)} non-required CI check(s) failed: "
                    f"{', '.join(failed_non_required)}"
                )
                ci_passing = False
            if pending_non_required:
                reasons.append(
                    f"{len(pending_non_required)} non-required CI check(s) pending: "
                    f"{', '.join(pending_non_required)}"
                )
                ci_passing = False

    can_merge = len(reasons) == 0

    return {
        "Success": True,
        "CanMerge": can_merge,
        "PullRequest": pr_number,
        "Owner": owner,
        "Repo": repo,
        "State": pr["state"],
        "IsDraft": pr.get("isDraft", False),
        "Mergeable": mergeable,
        "MergeStateStatus": pr.get("mergeStateStatus", ""),
        "UnresolvedThreads": unresolved_count,
        "TotalThreads": total_threads,
        "FailedRequiredChecks": failed_required,
        "PendingRequiredChecks": pending_required,
        "FailedNonRequiredChecks": failed_non_required,
        "PendingNonRequiredChecks": pending_non_required,
        "PassedChecks": passed_checks,
        "CIPassing": ci_passing,
        "IncludeNonRequired": include_non_required,
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
