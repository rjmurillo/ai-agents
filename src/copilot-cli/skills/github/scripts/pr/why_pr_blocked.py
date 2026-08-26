#!/usr/bin/env python3
# mypy: disable-error-code="no-any-return,type-arg", follow-imports=skip
# taste-lint: ignore file-size, standalone plugin script keeps one portable entry point.
# taste-lint: ignore complexity, main maps independent gate states to exit classes.
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
    1 - Blocking cause found (missing, failing, pending, or unresolved threads)
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
    extract_workflow_run_number,
    fetch_ruleset_required_contexts,
    find_missing_required,
    partition_rows_by_run,
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
            baseRefName
            mergeStateStatus
            commits(last: 1) {
                nodes {
                    commit {
                        oid
                        statusCheckRollup {
                            state
                            contexts(first: 100) {
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
                                            }
                                        }
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
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    isResolved
                    isOutdated
                }
            }
        }
    }
}"""

_CONTEXTS_PAGE_QUERY = """\
query(
    $owner: String!,
    $repo: String!,
    $oid: GitObjectID!,
    $number: Int!,
    $cursor: String!
) {
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
                                    }
                                }
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
}"""

_THREADS_PAGE_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!, $cursor: String!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            reviewThreads(first: 100, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    isResolved
                    isOutdated
                }
            }
        }
    }
}"""

_MAX_PAGES = 100

# Passing conclusions per get_pr_checks.py semantics.
_PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
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


def _is_pending_check(node: dict) -> bool:
    typename = node.get("__typename")
    if typename == "CheckRun":
        return node.get("status", "") in {
            "QUEUED",
            "IN_PROGRESS",
            "WAITING",
            "PENDING",
            "REQUESTED",
        }
    if typename == "StatusContext":
        return node.get("state", "") in {"PENDING", "EXPECTED"}
    return False


def _check_name(node: dict) -> str:
    if node.get("__typename") == "CheckRun":
        return node.get("name", "")
    return node.get("context", "")


def _workflow_key(node: dict) -> tuple[int, int] | None:
    if node.get("__typename") != "CheckRun":
        return None
    workflow_run = ((node.get("checkSuite") or {}).get("workflowRun") or {})
    run_number = workflow_run.get("databaseId")
    if run_number is None:
        run_number = extract_workflow_run_number(node.get("detailsUrl"))
    if run_number is None:
        return None
    attempt = workflow_run.get("runAttempt")
    return int(run_number), int(attempt) if attempt is not None else 1


def _classify_rows(nodes: list[dict]) -> str:
    if any(_is_failing_check(node) for node in nodes):
        return "failing"
    if any(_is_pending_check(node) for node in nodes):
        return "pending"
    if nodes and all(_is_passing_check(node) for node in nodes):
        return "passing"
    return "unknown"


def _most_blocking_state(states: list[str]) -> str:
    for state in ("failing", "pending", "unknown", "passing"):
        if state in states:
            return state
    return "unknown"


def _classify_same_name_rows(nodes: list[dict]) -> str:
    """Return the current state for one required-check name."""
    check_runs = [node for node in nodes if node.get("__typename") == "CheckRun"]
    if not check_runs:
        return _classify_rows(nodes)

    prepared = []
    for node in check_runs:
        run_key = _workflow_key(node)
        prepared.append(
            {
                **node,
                "_workflow_run_id": run_key[0] if run_key else None,
                "_workflow_run_attempt": run_key[1] if run_key else None,
            }
        )

    candidates = [
        (
            _workflow_key(group[0]),
            _classify_rows(group),
            any(node.get("isRequired") for node in group),
        )
        for group in partition_rows_by_run(
            prepared,
            "detailsUrl",
            "_workflow_run_id",
            "_workflow_run_attempt",
        )
    ]
    if any(is_required for _, _, is_required in candidates):
        candidates = [
            candidate for candidate in candidates
            if candidate[2]
        ]
    known = [
        (key, state)
        for key, state, _ in candidates
        if key is not None
    ]
    unknown_states = [
        state for key, state, _ in candidates
        if key is None
    ]
    if known:
        latest_key = max(key for key, _ in known)
        current_states = [state for key, state in known if key == latest_key]
        return _most_blocking_state(current_states + unknown_states)
    return _most_blocking_state(unknown_states)


def _fetch_remaining_contexts(
    owner: str,
    repo: str,
    pr_number: int,
    oid: str,
    page_info: dict,
) -> tuple[list[dict], bool]:
    nodes: list[dict] = []
    seen_cursors: set[str] = set()
    for _ in range(_MAX_PAGES):
        if not page_info.get("hasNextPage"):
            return nodes, True
        cursor = page_info.get("endCursor")
        if not cursor or cursor in seen_cursors or not oid:
            return nodes, False
        seen_cursors.add(cursor)
        data = gh_graphql(
            _CONTEXTS_PAGE_QUERY,
            {
                "owner": owner,
                "repo": repo,
                "oid": oid,
                "number": pr_number,
                "cursor": cursor,
            },
        )
        repository = data.get("repository")
        commit_obj = repository.get("object") if isinstance(repository, dict) else None
        rollup = (
            commit_obj.get("statusCheckRollup")
            if isinstance(commit_obj, dict)
            else None
        )
        contexts = rollup.get("contexts") if isinstance(rollup, dict) else None
        if not isinstance(contexts, dict) or "pageInfo" not in contexts:
            return nodes, False
        nodes.extend(contexts.get("nodes") or [])
        page_info = contexts.get("pageInfo") or {}
    return nodes, not page_info.get("hasNextPage")


def _fetch_remaining_threads(
    owner: str,
    repo: str,
    pr_number: int,
    page_info: dict,
) -> tuple[list[dict], bool]:
    nodes: list[dict] = []
    seen_cursors: set[str] = set()
    for _ in range(_MAX_PAGES):
        if not page_info.get("hasNextPage"):
            return nodes, True
        cursor = page_info.get("endCursor")
        if not cursor or cursor in seen_cursors:
            return nodes, False
        seen_cursors.add(cursor)
        data = gh_graphql(
            _THREADS_PAGE_QUERY,
            {
                "owner": owner,
                "repo": repo,
                "number": pr_number,
                "cursor": cursor,
            },
        )
        repository = data.get("repository")
        pr = (
            repository.get("pullRequest")
            if isinstance(repository, dict)
            else None
        )
        threads = pr.get("reviewThreads") if isinstance(pr, dict) else None
        if not isinstance(threads, dict) or "pageInfo" not in threads:
            return nodes, False
        nodes.extend(threads.get("nodes") or [])
        page_info = threads.get("pageInfo") or {}
    return nodes, not page_info.get("hasNextPage")


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
        contexts = rollup.get("contexts") or {}
        rollup_nodes = list(contexts.get("nodes") or [])
        try:
            extra_nodes, complete = _fetch_remaining_contexts(
                owner,
                repo,
                pr_number,
                commit_obj.get("oid", ""),
                contexts.get("pageInfo") or {},
            )
        except RuntimeError as exc:
            return {"Error": "ApiError", "Message": f"GraphQL failed: {exc}"}
        if not complete:
            return {
                "Error": "ApiError",
                "Message": "Status-check pagination did not complete",
            }
        rollup_nodes.extend(extra_nodes)

    threads = pr.get("reviewThreads") or {}
    thread_nodes = list(threads.get("nodes") or [])
    try:
        extra_threads, complete = _fetch_remaining_threads(
            owner,
            repo,
            pr_number,
            threads.get("pageInfo") or {},
        )
    except RuntimeError as exc:
        return {"Error": "ApiError", "Message": f"GraphQL failed: {exc}"}
    if not complete:
        return {
            "Error": "ApiError",
            "Message": "Review-thread pagination did not complete",
        }
    thread_nodes.extend(extra_threads)

    return {
        "BaseBranch": pr.get("baseRefName"),
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

    Groups check nodes by name and workflow run. Same-run failures win, and
    the latest identified workflow run determines the current result.
    """
    nodes = pr_data.get("CheckNodes") or []

    nodes_by_name: dict[str, list[dict]] = {}
    required_names: set[str] = set()

    for node in nodes:
        name = _check_name(node)
        nodes_by_name.setdefault(name, []).append(node)
        if node.get("isRequired"):
            required_names.add(name)

    states_by_name = {
        name: _classify_same_name_rows(name_nodes)
        for name, name_nodes in nodes_by_name.items()
        if name in required_names
    }
    failing_required = sorted(
        name for name, state in states_by_name.items() if state == "failing"
    )
    pending_required = sorted(
        name for name, state in states_by_name.items() if state == "pending"
    )
    indeterminate_required = sorted(
        name for name, state in states_by_name.items() if state == "unknown"
    )

    reported_names = required_names
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
        "PendingRequired": pending_required,
        "IndeterminateRequired": indeterminate_required,
        "UnresolvedThreads": unresolved_count,
        "BaseBranch": pr_data.get("BaseBranch"),
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
        "--base-branch", default=None,
        help="Base branch to read the ruleset from (default: PR base branch). "
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

    base_branch = (
        args.base_branch.strip()
        if args.base_branch is not None
        else str(pr_data.get("BaseBranch") or "")
    )
    ruleset_contexts: list[str] | None = None
    if base_branch:
        ruleset_contexts = fetch_ruleset_required_contexts(owner, repo, base_branch)

    if base_branch and ruleset_contexts is None:
        write_skill_error(
            f"Failed to read required checks for base branch {base_branch!r}",
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
    pending = result["PendingRequired"]
    indeterminate = result["IndeterminateRequired"]
    unresolved = result["UnresolvedThreads"]

    has_hard_blocker = bool(
        missing
        or failing
        or indeterminate
        or unresolved
        or result["MergeStateStatus"] == "DIRTY"
    )
    has_blocker = has_hard_blocker or bool(pending)
    number = args.pull_request

    if not has_blocker:
        summary = (
            f"PR #{number}: no blocking cause found "
            "(no missing, failing, pending, or indeterminate required checks; "
            "no unresolved threads). "
            "PR may be mergeable regardless of mergeStateStatus."
        )
        status = "PASS"
    else:
        parts = []
        if missing:
            parts.append(f"{len(missing)} missing required check(s)")
        if failing:
            parts.append(f"{len(failing)} failing required check(s)")
        if pending:
            parts.append(f"{len(pending)} pending required check(s)")
        if indeterminate:
            parts.append(f"{len(indeterminate)} indeterminate required check(s)")
        if unresolved:
            parts.append(f"{unresolved} unresolved review thread(s)")
        if result["MergeStateStatus"] == "DIRTY":
            parts.append("merge conflicts")
        summary = f"PR #{number} blocked: {', '.join(parts)}"
        status = "FAIL"

    output = {
        "Number": number,
        "Owner": owner,
        "Repo": repo,
        "BaseBranch": result["BaseBranch"],
        "MergeStateStatus": result["MergeStateStatus"],
        "OverallState": result["OverallState"],
        "MissingRequired": missing,
        "FailingRequired": failing,
        "PendingRequired": pending,
        "IndeterminateRequired": indeterminate,
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

    if has_hard_blocker or pending:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
