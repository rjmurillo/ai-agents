#!/usr/bin/env python3
"""Check if a PR is ready to merge.

Performs comprehensive merge readiness check:
- Verifies all review threads are resolved
- Checks CI status (required checks passing by default)
- Validates PR state (open, not draft)
- Checks for merge conflicts

By default, only REQUIRED checks block merge. Non-required failing checks
are reported but do not affect CanMerge unless --include-non-required is set.

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
                for ctx in contexts:
                    typename = ctx.get("__typename")

                    if typename == "CheckRun":
                        name = ctx.get("name", "unknown")
                        status = ctx.get("status", "")
                        conclusion = ctx.get("conclusion", "")
                        is_required = ctx.get("isRequired", False)

                        if status != "COMPLETED":
                            if is_required:
                                pending_required.append(name)
                            else:
                                pending_non_required.append(name)
                        elif conclusion not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
                            if is_required:
                                failed_required.append(name)
                            else:
                                failed_non_required.append(name)
                        else:
                            passed_checks += 1

                    elif typename == "StatusContext":
                        name = ctx.get("context", "unknown")
                        state = ctx.get("state", "")
                        is_required = ctx.get("isRequired", False)

                        if state == "PENDING":
                            if is_required:
                                pending_required.append(name)
                            else:
                                pending_non_required.append(name)
                        elif state not in ("SUCCESS", "EXPECTED"):
                            if is_required:
                                failed_required.append(name)
                            else:
                                failed_non_required.append(name)
                        else:
                            passed_checks += 1

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
