#!/usr/bin/env python3
# mypy: disable-error-code="no-any-return,type-arg", follow-imports=skip
"""Diagnose why a PR is blocked from merging.

Cross-references the base branch ruleset against the PR's actual status check
rollup and unresolved review threads to produce a discriminated cause list:
MISSING checks, FAILING checks, and unresolved threads.

When nothing is missing, nothing is failing, and no thread is unresolved, the
script says so explicitly, because that is the signal that the PR is actually
mergeable regardless of mergeStateStatus. (GitHub reports BLOCKED even for PRs
that merge cleanly on the first call -- refs issue #4393.)

Exit codes (ADR-035):
    0 - No blocking cause found (PR may be mergeable)
    1 - Blocking cause found (missing, failing, or unresolved threads)
    2 - PR not found or config error
    3 - API error
"""

from __future__ import annotations

import argparse
import os
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)

if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
)
from github_core.checks_rollup import (
    fetch_ruleset_required_contexts,
    find_missing_required,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# ---------------------------------------------------------------------------
# GraphQL query: PR status + unresolved threads
# ---------------------------------------------------------------------------

_PR_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            mergeStateStatus
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
            reviewThreads(first: 100) {
                nodes {
                    isResolved
                    isOutdated
                }
            }
        }
    }
}"""

# Passing conclusions per get_pr_checks.py semantics.
_PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL"}
_PASSING_STATES = {"SUCCESS"}


def _is_passing_check(node: dict) -> bool:
    typename = node.get("__typename")
    if typename == "CheckRun":
        return node.get("conclusion", "") in _PASSING_CONCLUSIONS
    if typename == "StatusContext":
        return node.get("state", "") in _PASSING_STATES
    return False


def _is_failing_check(node: dict) -> bool:
    typename = node.get("__typename")
    if typename == "CheckRun":
        status = node.get("status", "")
        conclusion = node.get("conclusion", "")
        if status in {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}:
            return False
        return conclusion not in _PASSING_CONCLUSIONS and bool(conclusion)
    if typename == "StatusContext":
        return node.get("state", "") in {"FAILURE", "ERROR"}
    return False


def _check_name(node: dict) -> str:
    if node.get("__typename") == "CheckRun":
        return node.get("name", "")
    return node.get("context", "")


def fetch_pr_data(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch PR status checks and review threads via GraphQL."""
    try:
        data = gh_graphql(
            _PR_QUERY,
            {"owner": owner, "repo": repo, "number": pr_number},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg or "not found" in msg:
            return {"Error": "NotFound", "Message": f"PR #{pr_number} not found"}
        return {"Error": "ApiError", "Message": f"GraphQL failed: {msg}"}

    pr = (data.get("repository") or {}).get("pullRequest")
    if pr is None:
        return {"Error": "NotFound", "Message": "PR not found in response"}

    commits = (pr.get("commits") or {}).get("nodes") or []
    rollup_nodes: list[dict] = []
    overall_state = "UNKNOWN"
    if commits:
        commit_obj = (commits[0].get("commit") or {})
        rollup = commit_obj.get("statusCheckRollup") or {}
        overall_state = rollup.get("state", "UNKNOWN")
        rollup_nodes = (rollup.get("contexts") or {}).get("nodes") or []

    thread_nodes = (pr.get("reviewThreads") or {}).get("nodes") or []

    return {
        "MergeStateStatus": pr.get("mergeStateStatus"),
        "OverallState": overall_state,
        "CheckNodes": rollup_nodes,
        "ThreadNodes": thread_nodes,
    }


def diagnose(
    pr_data: dict,
    ruleset_contexts: list[str] | None,
) -> dict:
    """Compute (missing, failing, unresolved_thread_count) from raw PR data.

    Groups check nodes by name: SUCCESS on any row for a name wins over a
    FAILURE row (re-run semantics). Never let a later row overwrite a SUCCESS.
    """
    nodes = pr_data.get("CheckNodes") or []

    # Group by name: track best passing or failing per name.
    passing_names: set[str] = set()
    failing_by_name: dict[str, bool] = {}
    required_names: set[str] = set()

    for node in nodes:
        name = _check_name(node)
        if node.get("isRequired"):
            required_names.add(name)
        if _is_passing_check(node):
            passing_names.add(name)
            failing_by_name.pop(name, None)  # SUCCESS beats FAILURE
        elif _is_failing_check(node) and name not in passing_names:
            failing_by_name[name] = True

    failing_required = sorted(
        n for n in failing_by_name if n in required_names
    )

    reported_names = {_check_name(n) for n in nodes}
    missing_required: list[str] = []
    if ruleset_contexts is not None:
        missing_required = find_missing_required(ruleset_contexts, reported_names)

    thread_nodes = pr_data.get("ThreadNodes") or []
    unresolved_count = sum(
        1 for t in thread_nodes
        if not t.get("isResolved") and not t.get("isOutdated")
    )

    return {
        "MissingRequired": missing_required,
        "FailingRequired": failing_required,
        "UnresolvedThreads": unresolved_count,
        "OverallState": pr_data.get("OverallState", "UNKNOWN"),
        "MergeStateStatus": pr_data.get("MergeStateStatus"),
        "RulesetContextsAvailable": ruleset_contexts is not None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose why a PR is blocked from merging.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True,
        help="PR number",
    )
    parser.add_argument(
        "--base-branch", default="main",
        help="Base branch to read the ruleset from (default: main). "
             "Pass empty string to skip ruleset fetch.",
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

    base_branch = args.base_branch.strip() if args.base_branch else ""
    ruleset_contexts: list[str] | None = None
    if base_branch:
        ruleset_contexts = fetch_ruleset_required_contexts(owner, repo, base_branch)

    pr_data = fetch_pr_data(owner, repo, args.pull_request)

    if pr_data.get("Error") == "NotFound":
        write_skill_error(
            pr_data["Message"],
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name="why_pr_blocked.py",
            extra={"Number": args.pull_request},
        )
        return 2

    if pr_data.get("Error") == "ApiError":
        write_skill_error(
            pr_data["Message"],
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="why_pr_blocked.py",
            extra={"Number": args.pull_request},
        )
        return 3

    result = diagnose(pr_data, ruleset_contexts)

    missing = result["MissingRequired"]
    failing = result["FailingRequired"]
    unresolved = result["UnresolvedThreads"]

    has_blocker = bool(missing or failing or unresolved)
    number = args.pull_request

    if not has_blocker:
        summary = (
            f"PR #{number}: no blocking cause found "
            "(no missing, no failing required checks, no unresolved threads). "
            "PR may be mergeable regardless of mergeStateStatus."
        )
        status = "PASS"
    else:
        parts = []
        if missing:
            parts.append(f"{len(missing)} missing required check(s)")
        if failing:
            parts.append(f"{len(failing)} failing required check(s)")
        if unresolved:
            parts.append(f"{unresolved} unresolved review thread(s)")
        summary = f"PR #{number} blocked: {', '.join(parts)}"
        status = "FAIL"

    output = {
        "Number": number,
        "Owner": owner,
        "Repo": repo,
        "MergeStateStatus": result["MergeStateStatus"],
        "OverallState": result["OverallState"],
        "MissingRequired": missing,
        "FailingRequired": failing,
        "UnresolvedThreads": unresolved,
        "HasBlocker": has_blocker,
        "RulesetContextsAvailable": result["RulesetContextsAvailable"],
    }

    write_skill_output(
        output,
        output_format=fmt,
        human_summary=summary,
        status=status,
        script_name="why_pr_blocked.py",
    )

    return 1 if has_blocker else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
