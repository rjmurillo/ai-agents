#!/usr/bin/env python3
"""Get CI check status for a GitHub Pull Request.

Retrieves CI check information using GraphQL statusCheckRollup API.
Returns structured JSON with check states, conclusions, and summary counts.

Exit codes (ADR-035):
    0 = All checks passing (or pending)
    1 = One or more checks failed
    2 = PR not found
    3 = API error
    4 = Not authenticated
    7 = Timeout reached (with --wait)
"""

import argparse
import json
import os
import sys
import time

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
)

QUERY = """
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
}
"""

PENDING_STATES = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED", "EXPECTED"}
PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
FAILING_CONCLUSIONS = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "ERROR"}


def normalize_check(ctx: dict) -> dict | None:
    """Convert a GraphQL context node to a normalized check dict."""
    typename = ctx.get("__typename")

    if typename == "CheckRun":
        status = ctx.get("status", "")
        conclusion = ctx.get("conclusion", "")
        return {
            "Name": ctx.get("name"),
            "Type": "CheckRun",
            "State": status,
            "Conclusion": conclusion,
            "DetailsUrl": ctx.get("detailsUrl"),
            "IsRequired": ctx.get("isRequired", False),
            "IsPending": status in PENDING_STATES,
            "IsPassing": conclusion in PASSING_CONCLUSIONS,
            "IsFailing": conclusion in FAILING_CONCLUSIONS,
        }

    if typename == "StatusContext":
        state = ctx.get("state", "")
        return {
            "Name": ctx.get("context"),
            "Type": "StatusContext",
            "State": state,
            "Conclusion": state,
            "DetailsUrl": ctx.get("targetUrl"),
            "IsRequired": ctx.get("isRequired", False),
            "IsPending": state in PENDING_STATES,
            "IsPassing": state == "SUCCESS",
            "IsFailing": state in {"FAILURE", "ERROR"},
        }

    return None


def fetch_checks(owner: str, repo: str, number: int, required_only: bool = False) -> dict:
    """Fetch and normalize PR checks."""
    try:
        data = gh_graphql(QUERY, {"owner": owner, "repo": repo, "number": number})
    except Exception as e:
        error_msg = str(e)
        if "Could not resolve" in error_msg or "not found" in error_msg:
            return {"error": "NotFound", "message": f"PR #{number} not found in {owner}/{repo}"}
        return {"error": "ApiError", "message": f"GraphQL query failed: {error_msg}"}

    pr = data.get("repository", {}).get("pullRequest")
    if not pr:
        return {"error": "NotFound", "message": "PR not found in response"}

    commits = pr.get("commits", {}).get("nodes", [])
    if not commits:
        return {"number": number, "checks": [], "overall_state": "UNKNOWN", "has_checks": False}

    rollup = commits[0].get("commit", {}).get("statusCheckRollup")
    if not rollup:
        return {"number": number, "checks": [], "overall_state": "UNKNOWN", "has_checks": False}

    contexts = rollup.get("contexts", {}).get("nodes", [])
    checks = []
    for ctx in contexts:
        check = normalize_check(ctx)
        if check:
            if required_only and not check["IsRequired"]:
                continue
            checks.append(check)

    return {
        "number": number,
        "checks": checks,
        "overall_state": rollup.get("state", "UNKNOWN"),
        "has_checks": True,
    }


def build_output(check_data: dict, owner: str, repo: str) -> dict:
    """Build the final output object."""
    checks = check_data.get("checks", [])
    failed = sum(1 for c in checks if c.get("IsFailing"))
    pending = sum(1 for c in checks if c.get("IsPending"))
    passed = sum(1 for c in checks if c.get("IsPassing"))
    has_checks = check_data.get("has_checks", False)
    all_passing = has_checks and checks and failed == 0 and pending == 0

    return {
        "Success": True,
        "Number": check_data.get("number"),
        "Owner": owner,
        "Repo": repo,
        "OverallState": check_data.get("overall_state", "UNKNOWN"),
        "HasChecks": has_checks,
        "Checks": [
            {"Name": c["Name"], "State": c["State"], "Conclusion": c["Conclusion"],
             "DetailsUrl": c["DetailsUrl"], "IsRequired": c["IsRequired"]}
            for c in checks
        ],
        "FailedCount": failed,
        "PendingCount": pending,
        "PassedCount": passed,
        "AllPassing": all_passing,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Get PR CI check status")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument("--wait", action="store_true", help="Poll until checks complete")
    parser.add_argument(
        "--timeout-seconds", type=int, default=300,
        help="Max wait time (default: 300)",
    )
    parser.add_argument("--required-only", action="store_true", help="Filter to required checks")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    start = time.time()

    while True:
        check_data = fetch_checks(owner, repo, args.pull_request, args.required_only)

        if "error" in check_data:
            exit_code = 2 if check_data["error"] == "NotFound" else 3
            output = {"Success": False, "Error": check_data["message"], "Number": args.pull_request}
            print(json.dumps(output, indent=2))
            sys.exit(exit_code)

        output = build_output(check_data, owner, repo)

        if not args.wait or output["PendingCount"] == 0:
            break

        elapsed = time.time() - start
        if elapsed >= args.timeout_seconds:
            print(json.dumps(output, indent=2))
            pending = output['PendingCount']
            timeout = args.timeout_seconds
            print(
                f"Timeout: {pending} checks still pending"
                f" after {timeout}s",
                file=sys.stderr,
            )
            sys.exit(7)

        time.sleep(10)

    print(json.dumps(output, indent=2))

    pr_num = output['Number']
    if output["FailedCount"] > 0:
        failed = output['FailedCount']
        print(
            f"PR #{pr_num}: {failed} check(s) failed",
            file=sys.stderr,
        )
        sys.exit(1)
    elif output["PendingCount"] > 0:
        pending = output['PendingCount']
        print(
            f"PR #{pr_num}: {pending} check(s) still pending",
            file=sys.stderr,
        )
    else:
        passed = output['PassedCount']
        print(
            f"PR #{pr_num}: All {passed} check(s) passing",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
