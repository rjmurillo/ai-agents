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
                        statusCheckRollup {
                            state
                            contexts(first: 100) {
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

# Pending statuses for CheckRun
_PENDING_STATUSES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}
# Passing conclusions for CheckRun
_PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
# Failing conclusions for CheckRun
_FAILING_CONCLUSIONS = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}


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
# last concrete failure. The pending signal is still retained for wait polling.
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


def _check_rank(check: dict) -> int:
    """Rank a normalized check by precedence: passing < failing < pending."""
    if check.get("IsPassing"):
        return _PASSING_RANK
    if check.get("IsFailing"):
        return _FAILING_RANK
    if check.get("IsPending"):
        return _PENDING_RANK
    return _FAILING_RANK


def dedupe_checks(checks: list[dict]) -> list[dict]:
    """Collapse multiple runs of one check name to the winning entry.

    Groups by ``Name`` and keeps the entry with the best precedence
    (passing over failing over pending), so a re-run SUCCESS supersedes a
    stale FAILURE on the same commit. The first-seen order of surviving
    names is preserved. Required-check status is retained when any duplicate
    row for a name is required.
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
        elif _check_rank(check) < _check_rank(current):
            best_by_name[name] = check

    deduped = []
    for name in order:
        winner = {**best_by_name[name], "IsRequired": required_by_name[name]}
        if not winner.get("IsPassing") and pending_by_name[name]:
            winner["IsPending"] = True
        deduped.append(winner)
    return deduped


# ---------------------------------------------------------------------------
# Query and parse
# ---------------------------------------------------------------------------


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
    rollup = commit.get("commit", {}).get("statusCheckRollup")
    if not rollup:
        return {
            "Number": pr.get("number"),
            "Checks": [],
            "OverallState": "UNKNOWN",
            "HasChecks": False,
        }

    overall_state = rollup.get("state", "UNKNOWN")
    context_nodes = rollup.get("contexts", {}).get("nodes", [])

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
    }


def build_output(
    check_data: dict,
    owner: str,
    repo: str,
    required_only: bool = False,
) -> dict:
    """Build the final output object from check data."""
    checks = check_data.get("Checks", [])
    if required_only:
        checks = [c for c in checks if c.get("IsRequired")]

    failed_count = sum(1 for c in checks if c.get("IsFailing"))
    pending_count = sum(1 for c in checks if c.get("IsPending"))
    passed_count = sum(1 for c in checks if c.get("IsPassing"))

    has_checks = check_data.get("HasChecks", False)
    all_passing = (
        has_checks
        and len(checks) > 0
        and failed_count == 0
        and pending_count == 0
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
            for c in checks
        ],
        "FailedCount": failed_count,
        "PendingCount": pending_count,
        "PassedCount": passed_count,
        "AllPassing": all_passing,
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

        # If not waiting, or no pending checks, we are done
        if not args.wait or output["PendingCount"] == 0:
            break

        # Check timeout
        elapsed = time.monotonic() - start_time
        if elapsed >= args.timeout_seconds:
            write_skill_output(
                output,
                output_format=fmt,
                human_summary=(
                    f"Timeout: {output['PendingCount']} checks still pending "
                    f"after {args.timeout_seconds} seconds"
                ),
                status="WARNING",
                script_name="get_pr_checks.py",
            )
            return 7

        if iteration >= max_iterations:
            break

        time.sleep(10)

    # Determine status for human output
    if output["FailedCount"] > 0:
        summary = f"PR #{output['Number']}: {output['FailedCount']} check(s) failed"
        status = "FAIL"
    elif output["PendingCount"] > 0:
        summary = f"PR #{output['Number']}: {output['PendingCount']} check(s) still pending"
        status = "WARNING"
    else:
        summary = f"PR #{output['Number']}: All {output['PassedCount']} check(s) passing"
        status = "PASS"

    write_skill_output(
        output,
        output_format=fmt,
        human_summary=summary,
        status=status,
        script_name="get_pr_checks.py",
    )

    if output["FailedCount"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
