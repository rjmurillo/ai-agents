#!/usr/bin/env python3
# mypy: disable-error-code="no-any-return,type-arg", follow-imports=skip
# taste-lint: ignore file-size, standalone plugin script keeps one portable entry point (same shape as why_pr_blocked.py); the GraphQL queries and verdict contract must travel together.
"""Answer "is this failing PR check also red on origin/main?" before triage.

CI-failure triage step 1 (issue #5073). When a PR check goes red, the cause
frequently lives on main: a whole-repo ratchet crossed its own baseline, a
gate merged red against its corpus, a flaky dependency broke every branch.
Four recorded investigations each burned about 13 CI-minutes before
discovering the cause lived on main
(.serena/memories/ci/measure-main-before-blaming-the-pr.md in the
rjmurillo/ai-agents repository). This probe makes attribution the first
step instead of the last.

Given a check name as it appears on the PR, the script walks origin/main's
recent commits newest-first and reports the latest completed run of the same
check name, with the run's URL as evidence. Three verdicts:

- GREEN_ON_MAIN: the check passes on main's latest completed run. The
  failure is introduced by the PR; investigate the PR.
- RED_ON_MAIN: the check fails on main's latest completed run. The failure
  is inherited; cite EvidenceUrl instead of debugging the PR.
- UNKNOWN: the probe could not determine main's state (API failure,
  incomplete pagination, or the check never reported on recent main
  commits, which happens for pull_request-only workflows). Probe failure is
  not absence: UNKNOWN is never reported as green.

Check names are GitHub job names and are not unique across workflows in
this repository (eleven display names are shared by two or more job
definitions; see
.serena/memories/ci/ci-job-names-collide-so-a-red-check-name-is-ambiguous.md
in the rjmurillo/ai-agents repository). When more than one workflow run
reports the name on the evidence commit, any red run wins and
AmbiguousDefinitions is set so the caller knows the name did not identify a
single job.

Conclusion classification. The canonical failing set is quoted verbatim from
the sibling script get_pr_checks.py:

    _FAILING_CONCLUSIONS = {
        "FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED",
        "STALE", "STARTUP_FAILURE",
    }

Stricter/looser/different than canonical: this script treats CANCELLED and
STALE as non-evidence rather than red. On main, concurrency groups cancel
superseded runs constantly (one measured 45-second window produced 20
cancelled runs), so a cancelled run proves nothing about whether the check
would pass. SKIPPED is likewise non-evidence here, not passing as in
get_pr_checks.py: a skipped run on main must never overwrite a SUCCESS or
stand in for one, so the probe keeps walking to an older commit instead
(refs the rollup-collapse trap in issue #4499).

Exit codes (ADR-035):
    0 - GREEN_ON_MAIN (check passes on main; investigate the PR)
    1 - RED_ON_MAIN (failure inherited from main; cite EvidenceUrl)
    2 - Config error (branch not found, invalid arguments)
    3 - UNKNOWN / API error (probe failure is not absence)
    4 - Auth error (from assert_gh_authenticated)
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
    partition_rows_by_run,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# ---------------------------------------------------------------------------
# GraphQL queries
# ---------------------------------------------------------------------------

_BRANCH_HISTORY_QUERY = """\
query($owner: String!, $repo: String!, $branch: String!, $depth: Int!) {
    repository(owner: $owner, name: $repo) {
        ref(qualifiedName: $branch) {
            name
            target {
                ... on Commit {
                    history(first: $depth) {
                        nodes {
                            oid
                            committedDate
                            statusCheckRollup {
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
                                        }
                                        ... on StatusContext {
                                            __typename
                                            context
                                            state
                                            targetUrl
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
}"""

_COMMIT_CONTEXTS_PAGE_QUERY = """\
query($owner: String!, $repo: String!, $oid: GitObjectID!, $cursor: String!) {
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
                            }
                            ... on StatusContext {
                                __typename
                                context
                                state
                                targetUrl
                            }
                        }
                    }
                }
            }
        }
    }
}"""

_MAX_CONTEXT_PAGES = 50

# See the module docstring for the verbatim canonical sets and the documented
# divergence (CANCELLED, STALE, and SKIPPED are non-evidence here).
_RED_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
_GREEN_CONCLUSIONS = {"SUCCESS", "NEUTRAL"}
_RED_STATUS_STATES = {"FAILURE", "ERROR"}
_GREEN_STATUS_STATES = {"SUCCESS"}

_VERDICT_GREEN = "GREEN_ON_MAIN"
_VERDICT_RED = "RED_ON_MAIN"
_VERDICT_UNKNOWN = "UNKNOWN"

_GUIDANCE = {
    _VERDICT_GREEN: (
        "Check is green on the base branch's latest completed run. "
        "The failure is introduced by the PR: investigate the PR."
    ),
    _VERDICT_RED: (
        "Check is red on the base branch. The failure is inherited from the "
        "base branch, not introduced by the PR: cite EvidenceUrl and fix or "
        "wait out the base branch instead of debugging the PR."
    ),
    _VERDICT_UNKNOWN: (
        "Could not determine the check's state on the base branch. Probe "
        "failure is not absence: do NOT treat this as green on the base "
        "branch."
    ),
}


# ---------------------------------------------------------------------------
# Row normalization and per-commit evaluation
# ---------------------------------------------------------------------------


def normalize_row(ctx: dict) -> dict | None:
    """Convert a GraphQL context node to a flat row, or None for other types.

    A malformed node (not a dict) is dropped rather than raised on: an
    AttributeError here would exit 1, which ADR-035 reserves for verified
    logic failures, and the caller's pagination completeness check already
    prevents a dropped node from turning into a false GREEN.
    """
    if not isinstance(ctx, dict):
        return None
    typename = ctx.get("__typename")

    if typename == "CheckRun":
        workflow_run = (ctx.get("checkSuite") or {}).get("workflowRun") or {}
        return {
            "Name": ctx.get("name", ""),
            "Type": "CheckRun",
            "Status": ctx.get("status", ""),
            "Conclusion": ctx.get("conclusion", ""),
            "DetailsUrl": ctx.get("detailsUrl", ""),
            "WorkflowRunId": workflow_run.get("databaseId"),
            "WorkflowRunAttempt": workflow_run.get("runAttempt"),
        }

    if typename == "StatusContext":
        return {
            "Name": ctx.get("context", ""),
            "Type": "StatusContext",
            "Status": "",
            "Conclusion": ctx.get("state", ""),
            "DetailsUrl": ctx.get("targetUrl", ""),
            "WorkflowRunId": None,
            "WorkflowRunAttempt": None,
        }

    return None


def _row_evidence(row: dict) -> str | None:
    """Classify one row as 'red', 'green', or None (no evidence)."""
    conclusion = row.get("Conclusion", "")
    if row.get("Type") == "StatusContext":
        if conclusion in _RED_STATUS_STATES:
            return "red"
        if conclusion in _GREEN_STATUS_STATES:
            return "green"
        return None
    if conclusion in _RED_CONCLUSIONS:
        return "red"
    if conclusion in _GREEN_CONCLUSIONS:
        return "green"
    return None


def _run_identity(row: dict) -> tuple[str, int] | None:
    """Return (run_id, attempt) for a CheckRun row, or None without provenance."""
    if row.get("Type") != "CheckRun":
        return None
    run_id = row.get("WorkflowRunId")
    if run_id is None:
        run_id = extract_workflow_run_number(row.get("DetailsUrl"))
    if run_id is None:
        return None
    attempt = row.get("WorkflowRunAttempt")
    return str(run_id), int(attempt) if attempt is not None else 1


def _latest_attempt_groups(groups: list[list[dict]]) -> list[list[dict]]:
    """Keep only the highest attempt per workflow run id.

    A rerun keeps the run id and bumps the attempt, so an older attempt's
    FAILURE must not outvote the latest attempt's SUCCESS. Groups without run
    provenance (StatusContext rows) pass through untouched.
    """
    best_by_run: dict[str, tuple[int, list[dict]]] = {}
    unkeyed: list[list[dict]] = []
    for group in groups:
        identity = _run_identity(group[0])
        if identity is None:
            unkeyed.append(group)
            continue
        run_id, attempt = identity
        current = best_by_run.get(run_id)
        if current is None or attempt > current[0]:
            best_by_run[run_id] = (attempt, group)
    return [group for _, group in best_by_run.values()] + unkeyed


def evaluate_commit_rows(rows: list[dict]) -> tuple[str | None, dict | None, bool]:
    """Evaluate one commit's same-named rows.

    Returns (verdict, evidence_row, ambiguous). Verdict is 'red', 'green', or
    None when the commit carries no completed evidence for the name (skipped,
    cancelled, stale, or still pending).

    Distinct workflow run ids are evaluated independently and any red run
    wins. Two runs with different ids on one base-branch commit are almost
    always two different workflows sharing a job name (the collision trap),
    and reporting the red one with its URL is the conservative direction:
    green is only claimed when every evidencing run is green.
    """
    groups = partition_rows_by_run(
        rows, "DetailsUrl", "WorkflowRunId", "WorkflowRunAttempt"
    )
    red_row: dict | None = None
    green_row: dict | None = None
    evidencing_runs = 0
    for group in _latest_attempt_groups(groups):
        group_red = next(
            (row for row in group if _row_evidence(row) == "red"), None
        )
        group_green = next(
            (row for row in group if _row_evidence(row) == "green"), None
        )
        if group_red is None and group_green is None:
            continue
        evidencing_runs += 1
        # Within one run, same-named rows are concurrent siblings, so a red
        # sibling wins over a green one (refs issue #4499).
        if group_red is not None:
            red_row = red_row or group_red
        else:
            green_row = green_row or group_green
    ambiguous = evidencing_runs > 1
    if red_row is not None:
        return "red", red_row, ambiguous
    if green_row is not None:
        return "green", green_row, ambiguous
    return None, None, False


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _fetch_remaining_contexts(
    owner: str, repo: str, oid: str, page_info: dict
) -> tuple[list[dict], bool]:
    """Fetch remaining status-check contexts for one commit by cursor."""
    nodes: list[dict] = []
    seen_cursors: set[str] = set()
    for _ in range(_MAX_CONTEXT_PAGES):
        if not page_info.get("hasNextPage"):
            return nodes, True
        cursor = page_info.get("endCursor")
        if not cursor or cursor in seen_cursors or not oid:
            return nodes, False
        seen_cursors.add(cursor)
        data = gh_graphql(
            _COMMIT_CONTEXTS_PAGE_QUERY,
            {"owner": owner, "repo": repo, "oid": oid, "cursor": cursor},
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


def fetch_branch_history(owner: str, repo: str, branch: str, depth: int) -> dict:
    """Fetch the branch's recent commits with their status-check contexts.

    Returns {"Commits": [...]} on success, where each commit is
    {"Oid", "CommittedDate", "ContextNodes", "PagesComplete"}, or an
    {"Error", "Message"} dict on failure.
    """
    try:
        data = gh_graphql(
            _BRANCH_HISTORY_QUERY,
            {
                "owner": owner,
                "repo": repo,
                "branch": f"refs/heads/{branch}",
                "depth": depth,
            },
        )
    except RuntimeError as exc:
        return {"Error": "ApiError", "Message": f"GraphQL failed: {exc}"}

    repository = data.get("repository")
    ref = repository.get("ref") if isinstance(repository, dict) else None
    if not isinstance(ref, dict):
        return {
            "Error": "BranchNotFound",
            "Message": f"Branch {branch!r} not found in {owner}/{repo}",
        }
    # Malformed shapes below map to ApiError (exit 3, UNKNOWN), never an
    # uncaught AttributeError: exit 1 is reserved for the RED_ON_MAIN verdict.
    target = ref.get("target")
    history = target.get("history") if isinstance(target, dict) else None
    history_nodes = history.get("nodes") if isinstance(history, dict) else None
    if not isinstance(history_nodes, list):
        return {
            "Error": "ApiError",
            "Message": "Malformed GraphQL response: branch history is missing",
        }

    commits: list[dict] = []
    for node in history_nodes:
        if not isinstance(node, dict):
            return {
                "Error": "ApiError",
                "Message": "Malformed GraphQL response: non-object history node",
            }
        # A null rollup or contexts is GitHub's legitimate "no checks on this
        # commit"; a non-null non-object is a malformed payload and must not
        # silently read as "no checks" (the walk would skip past it).
        rollup = node.get("statusCheckRollup")
        if rollup is not None and not isinstance(rollup, dict):
            return {
                "Error": "ApiError",
                "Message": "Malformed GraphQL response: non-object statusCheckRollup",
            }
        contexts = (rollup or {}).get("contexts")
        if contexts is not None and not isinstance(contexts, dict):
            return {
                "Error": "ApiError",
                "Message": "Malformed GraphQL response: non-object contexts",
            }
        contexts = contexts or {}
        context_nodes = list(contexts.get("nodes") or [])
        page_info = contexts.get("pageInfo") or {}
        pages_complete = True
        if page_info.get("hasNextPage"):
            try:
                extras, pages_complete = _fetch_remaining_contexts(
                    owner, repo, node.get("oid", ""), page_info
                )
            except RuntimeError as exc:
                return {"Error": "ApiError", "Message": f"GraphQL failed: {exc}"}
            context_nodes.extend(extras)
        commits.append(
            {
                "Oid": node.get("oid", ""),
                "CommittedDate": node.get("committedDate", ""),
                "ContextNodes": context_nodes,
                "PagesComplete": pages_complete,
            }
        )
    return {"Commits": commits}


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------


def triage(commits: list[dict], check_name: str) -> dict:
    """Walk commits newest-first and report the latest completed run's verdict.

    A commit with an incomplete context list stops the walk with UNKNOWN:
    the check's newest state may sit in the pages that never arrived, and an
    older commit's answer would misreport "latest". Probe failure is not
    absence.
    """
    commits_examined = 0
    for commit in commits:
        commits_examined += 1
        rows = [
            row
            for row in (normalize_row(ctx) for ctx in commit["ContextNodes"])
            if row is not None and row.get("Name") == check_name
        ]
        if not commit["PagesComplete"]:
            return {
                "Verdict": _VERDICT_UNKNOWN,
                "Reason": "contexts_incomplete",
                "EvidenceUrl": None,
                "EvidenceRunId": None,
                "EvidenceCommit": commit["Oid"],
                "EvidenceCommitDate": commit["CommittedDate"],
                "CommitsExamined": commits_examined,
                "AmbiguousDefinitions": False,
                "MatchedRows": rows,
            }
        verdict, evidence, ambiguous = evaluate_commit_rows(rows)
        if verdict is None:
            continue
        return {
            "Verdict": _VERDICT_RED if verdict == "red" else _VERDICT_GREEN,
            "Reason": "",
            "EvidenceUrl": (evidence or {}).get("DetailsUrl") or None,
            "EvidenceRunId": (evidence or {}).get("WorkflowRunId"),
            "EvidenceCommit": commit["Oid"],
            "EvidenceCommitDate": commit["CommittedDate"],
            "CommitsExamined": commits_examined,
            "AmbiguousDefinitions": ambiguous,
            "MatchedRows": rows,
        }
    return {
        "Verdict": _VERDICT_UNKNOWN,
        "Reason": "not_observed_on_branch",
        "EvidenceUrl": None,
        "EvidenceRunId": None,
        "EvidenceCommit": None,
        "EvidenceCommitDate": None,
        "CommitsExamined": commits_examined,
        "AmbiguousDefinitions": False,
        "MatchedRows": [],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Report whether a failing PR check is also red on the base "
            "branch's latest run (CI-failure triage step 1)."
        ),
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--check-name", required=True,
        help="Check name exactly as reported on the PR (job display name)",
    )
    parser.add_argument(
        "--branch", default="main",
        help="Base branch to measure (default: main)",
    )
    parser.add_argument(
        "--history-depth", type=int, default=15,
        help="How many recent base-branch commits to search for the latest "
             "run of the check (1-50, default: 15)",
    )
    parser.add_argument(
        "--pull-request", type=int, default=None,
        help="PR number the failing check was observed on (reporting context "
             "only; the probe reads the base branch, not the PR)",
    )
    add_output_format_arg(parser)
    return parser


def _summary(check_name: str, branch: str, result: dict) -> tuple[str, str]:
    """Return (human_summary, envelope_status) for the triage result."""
    verdict = result["Verdict"]
    if verdict == _VERDICT_GREEN:
        return (
            f"Check {check_name!r} is GREEN on {branch} "
            f"(commit {result['EvidenceCommit']}): investigate the PR",
            "PASS",
        )
    if verdict == _VERDICT_RED:
        return (
            f"Check {check_name!r} is RED on {branch}: inherited failure, "
            f"see {result['EvidenceUrl'] or 'the base branch run'}",
            "FAIL",
        )
    return (
        f"Check {check_name!r} state on {branch} is UNKNOWN "
        f"({result['Reason']}): probe failure is not absence, "
        "do not treat as green",
        "WARNING",
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    if not (1 <= args.history_depth <= 50):
        write_skill_error(
            f"--history-depth must be between 1 and 50, got {args.history_depth}",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="triage_red_check.py",
        )
        return 2

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    history = fetch_branch_history(owner, repo, args.branch, args.history_depth)

    if history.get("Error") == "BranchNotFound":
        write_skill_error(
            history["Message"],
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name="triage_red_check.py",
        )
        return 2
    if history.get("Error") == "ApiError":
        # An API failure is a probe failure, never evidence of green.
        write_skill_error(
            f"{history['Message']} (verdict: {_VERDICT_UNKNOWN}; probe "
            "failure is not absence, do not treat as green)",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="triage_red_check.py",
        )
        return 3

    result = triage(history["Commits"], args.check_name)
    verdict = result["Verdict"]

    # A check run can lack detailsUrl; the workflow run id still identifies
    # the evidence run, so construct the run URL rather than losing it.
    if not result["EvidenceUrl"] and result.get("EvidenceRunId") is not None:
        result["EvidenceUrl"] = (
            f"https://github.com/{owner}/{repo}/actions/runs/"
            f"{result['EvidenceRunId']}"
        )

    output = {
        "CheckName": args.check_name,
        "Branch": args.branch,
        "Owner": owner,
        "Repo": repo,
        "PullRequest": args.pull_request,
        "Verdict": verdict,
        "Guidance": _GUIDANCE[verdict],
        "Reason": result["Reason"],
        "EvidenceUrl": result["EvidenceUrl"],
        "EvidenceCommit": result["EvidenceCommit"],
        "EvidenceCommitDate": result["EvidenceCommitDate"],
        "CommitsExamined": result["CommitsExamined"],
        "AmbiguousDefinitions": result["AmbiguousDefinitions"],
        "MatchedRows": result["MatchedRows"],
    }

    summary, status = _summary(args.check_name, args.branch, result)
    write_skill_output(
        output,
        output_format=fmt,
        human_summary=summary,
        status=status,
        script_name="triage_red_check.py",
    )

    if verdict == _VERDICT_GREEN:
        return 0
    if verdict == _VERDICT_RED:
        return 1
    return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
