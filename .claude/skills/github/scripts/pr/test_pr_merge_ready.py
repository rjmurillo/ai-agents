#!/usr/bin/env python3
"""Check if a GitHub Pull Request is ready to merge.

Evaluates PR state, review threads, and CI status to determine
merge readiness. Returns structured JSON with blockers if any.

Exit codes (ADR-035):
    0 = Success (PR can merge)
    1 = PR cannot merge (blockers found)
    2 = PR not found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import sys

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
    write_error_and_exit,
)

QUERY = """
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
                nodes { id isResolved }
            }
            commits(last: 1) {
                nodes {
                    commit {
                        statusCheckRollup {
                            contexts(first: 100) {
                                nodes {
                                    ... on CheckRun {
                                        name
                                        conclusion
                                        isRequired(pullRequestNumber: $number)
                                    }
                                    ... on StatusContext {
                                        context
                                        state
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


def collect_failing_checks(
    contexts: list[dict],
    include_non_required: bool,
) -> list[dict]:
    """Return list of failing check info dicts."""
    failing = []
    for node in contexts:
        # CheckRun nodes have "conclusion" and "isRequired"
        if "conclusion" in node:
            is_required = node.get("isRequired", False)
            conclusion = node.get("conclusion")
            passed = conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED", None)
            if not passed and (is_required or include_non_required):
                failing.append({
                    "Name": node.get("name", "<unknown>"),
                    "Conclusion": conclusion,
                    "Required": is_required,
                })
        # StatusContext nodes have "state" and "context"
        elif "state" in node:
            state = node.get("state")
            if state not in ("SUCCESS", "PENDING"):
                failing.append({
                    "Name": node.get("context", "<unknown>"),
                    "Conclusion": state,
                    "Required": True,
                })
    return failing


def main() -> None:
    parser = argparse.ArgumentParser(description="Check if a PR is ready to merge")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")
    parser.add_argument("--ignore-ci", action="store_true", help="Ignore CI check status")
    parser.add_argument(
        "--ignore-threads", action="store_true",
        help="Ignore unresolved review threads",
    )
    parser.add_argument(
        "--include-non-required", action="store_true",
        help="Non-required check failures also block",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    try:
        data = gh_graphql(QUERY, {
            "owner": resolved["owner"],
            "repo": resolved["repo"],
            "number": args.pull_request,
        })
    except Exception as e:
        error_msg = str(e)
        if "Could not resolve" in error_msg:
            write_error_and_exit(f"PR #{args.pull_request} not found", 2)
        write_error_and_exit(f"GraphQL query failed: {error_msg}", 3)

    pr = data.get("repository", {}).get("pullRequest")
    if not pr:
        write_error_and_exit(
            f"PR #{args.pull_request} not found in {resolved['owner']}/{resolved['repo']}",
            2,
        )

    reasons: list[str] = []
    state = pr.get("state", "UNKNOWN")
    is_draft = pr.get("isDraft", False)
    mergeable = pr.get("mergeable", "UNKNOWN")

    if state != "OPEN":
        reasons.append(f"PR is {state}, not OPEN")
    if is_draft:
        reasons.append("PR is a draft")
    if mergeable == "CONFLICTING":
        reasons.append("PR has merge conflicts")

    # Unresolved threads
    thread_nodes = pr.get("reviewThreads", {}).get("nodes", [])
    unresolved_count = sum(1 for t in thread_nodes if not t.get("isResolved", False))
    if unresolved_count > 0 and not args.ignore_threads:
        reasons.append(f"{unresolved_count} unresolved review thread(s)")

    # CI checks
    failing_checks: list[dict] = []
    commits = pr.get("commits", {}).get("nodes", [])
    if commits:
        rollup = commits[0].get("commit", {}).get("statusCheckRollup")
        if rollup:
            contexts = rollup.get("contexts", {}).get("nodes", [])
            failing_checks = collect_failing_checks(contexts, args.include_non_required)
            if failing_checks and not args.ignore_ci:
                names = ", ".join(c["Name"] for c in failing_checks)
                reasons.append(f"Failing checks: {names}")

    can_merge = len(reasons) == 0

    output = {
        "Success": can_merge,
        "CanMerge": can_merge,
        "PullRequest": args.pull_request,
        "State": state,
        "IsDraft": is_draft,
        "Mergeable": mergeable,
        "UnresolvedThreads": unresolved_count,
        "FailingChecks": failing_checks,
        "Reasons": reasons,
    }

    print(json.dumps(output, indent=2))

    if can_merge:
        print(f"PR #{args.pull_request} is ready to merge", file=sys.stderr)
        sys.exit(0)
    else:
        for reason in reasons:
            print(f"  BLOCKER: {reason}", file=sys.stderr)
        num_blockers = len(reasons)
        print(
            f"PR #{args.pull_request} is NOT ready to merge"
            f" ({num_blockers} blocker(s))",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
