#!/usr/bin/env python3
"""PR discovery and classification for GitHub Actions matrix strategy."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.github_core.api import (  # noqa: E402
    RateLimitStatus,
    check_workflow_rate_limit,
    gh_graphql,
    resolve_repo_params,
)
from scripts.pr_maintenance_rollup import (  # noqa: E402
    complete_status_check_rollups,
    fetch_status_context_page_with_graphql,
    rollup_has_failing_checks,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROTECTED_BRANCHES = ("main", "master", "develop")

BOT_CATEGORIES: dict[str, list[str]] = {
    "agent-controlled": ["rjmurillo-bot", "rjmurillo[bot]"],
    "mention-triggered": [
        "copilot-swe-agent",
        "copilot-swe-agent[bot]",
        "copilot",
        "app/copilot-swe-agent",
    ],
    "review-bot": [
        "coderabbitai",
        "coderabbitai[bot]",
        "cursor[bot]",
        "gemini-code-assist",
        "gemini-code-assist[bot]",
    ],
}

# ---------------------------------------------------------------------------
# GraphQL query: fetch open PRs with status checks and review info
# ---------------------------------------------------------------------------

_OPEN_PRS_QUERY = """\
query($owner: String!, $name: String!, $limit: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequests(first: $limit, states: OPEN, orderBy: {field: UPDATED_AT, direction: DESC}) {
            nodes {
                number
                title
                author { login }
                headRefName
                baseRefName
                mergeable
                reviewDecision
                reviewRequests(first: 10) {
                    nodes {
                        requestedReviewer {
                            ... on User { login }
                            ... on Team { name }
                            ... on Bot { login }
                        }
                    }
                }
                reviewThreads(first: 100) {
                    totalCount
                    nodes {
                        isResolved
                    }
                }
                commits(last: 1) {
                    nodes {
                        commit {
                            oid
                            statusCheckRollup {
                                state
                                contexts(first: 100) {
                                    totalCount
                                    pageInfo { hasNextPage endCursor }
                                    nodes {
                                        ... on CheckRun { name conclusion startedAt completedAt }
                                        ... on StatusContext { context state createdAt }
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



def _fetch_status_context_page(
    owner: str,
    repo: str,
    oid: str,
    cursor: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return fetch_status_context_page_with_graphql(owner, repo, oid, cursor, gh_graphql)


def get_open_prs(owner: str, repo: str, limit: int = 20) -> list[dict[str, Any]]:
    """Fetch open PRs via GraphQL.

    Returns a list of PR node dicts. Returns an empty list on failure.
    """
    try:
        data = gh_graphql(
            _OPEN_PRS_QUERY,
            {"owner": owner, "name": repo, "limit": limit},
        )
    except RuntimeError:
        logger.exception("Failed to query open PRs")
        return []

    repository = data.get("repository")
    if repository is None:
        logger.error("Repository %s/%s not found in response", owner, repo)
        return []

    pull_requests = repository.get("pullRequests")
    if pull_requests is None:
        return []

    nodes: list[dict[str, Any]] = pull_requests.get("nodes", [])
    complete_status_check_rollups(owner, repo, nodes, _fetch_status_context_page)
    return nodes


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def classify_bot(author_login: str) -> dict[str, Any]:
    """Classify an author as bot or human.

    Returns {"is_bot": bool, "category": str, "name": str}.
    """
    login_lower = author_login.lower()

    for category, bot_names in BOT_CATEGORIES.items():
        for bot_name in bot_names:
            if login_lower == bot_name.lower() or login_lower.startswith(bot_name.lower()):
                return {"is_bot": True, "category": category, "name": author_login}

    return {"is_bot": False, "category": "human", "name": author_login}


def has_bot_reviewer(review_requests: dict[str, Any] | None) -> bool:
    """Check if any requested reviewer is an agent-controlled bot."""
    if not review_requests:
        return False

    nodes = review_requests.get("nodes", [])
    for request in nodes:
        reviewer = request.get("requestedReviewer")
        if not reviewer:
            continue
        login = reviewer.get("login")
        if not login:
            continue
        bot_info = classify_bot(login)
        if bot_info["is_bot"] and bot_info["category"] == "agent-controlled":
            return True

    return False


def has_conflicts(pr: dict[str, Any]) -> bool:
    """Return True if the PR has merge conflicts."""
    return pr.get("mergeable") == "CONFLICTING"


def has_failing_checks(pr: dict[str, Any]) -> bool:
    """Return True if the PR's latest commit has failing status checks."""
    commits = pr.get("commits")
    if not commits:
        return False

    nodes = commits.get("nodes", [])
    if not nodes:
        return False

    commit = nodes[0].get("commit")
    if not commit:
        return False

    rollup = commit.get("statusCheckRollup")
    if not rollup:
        return False

    return rollup_has_failing_checks(rollup, pr.get("number", "?"))


def has_unresolved_threads(pr: dict[str, Any]) -> bool:
    """Return True if the PR has unresolved review threads.

    Reads thread data from the bulk GraphQL query (zero additional API calls).
    A thread may be acknowledged (eyes reaction) but still unresolved.

    Part of the "Acknowledged vs Resolved" lifecycle model (Issue #974):
    - Eyes reaction = acknowledged for processing
    - Thread resolution = issue actually addressed
    """
    threads = pr.get("reviewThreads")
    if not threads:
        return False
    total = threads.get("totalCount", 0)
    nodes = threads.get("nodes", [])
    if total > len(nodes):
        logging.warning(
            "PR #%s has %d review threads but only %d fetched",
            pr.get("number", "?"), total, len(nodes),
        )
    for node in nodes:
        if not node:
            continue
        if not node.get("isResolved", True):
            return True
    return False


# ---------------------------------------------------------------------------
# Derivative detection
# ---------------------------------------------------------------------------


def get_derivative_prs(prs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return PRs that target non-protected branches (derivative PRs)."""
    derivatives: list[dict[str, Any]] = []
    for pr in prs:
        if pr.get("baseRefName") not in PROTECTED_BRANCHES:
            derivatives.append(
                {
                    "number": pr["number"],
                    "title": pr.get("title", ""),
                    "author": (pr.get("author") or {}).get("login", ""),
                    "targetBranch": pr.get("baseRefName", ""),
                    "sourceBranch": pr.get("headRefName", ""),
                }
            )
    return derivatives


def get_parents_with_derivatives(
    prs: list[dict[str, Any]], derivatives: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Map derivative PRs to their parent PRs."""
    parents: dict[int, dict[str, Any]] = {}

    for derivative in derivatives:
        target = derivative["targetBranch"]
        parent_pr = next((p for p in prs if p.get("headRefName") == target), None)
        if parent_pr is None:
            continue

        parent_number = parent_pr["number"]
        if parent_number in parents:
            parents[parent_number]["derivatives"].append(derivative["number"])
        else:
            parents[parent_number] = {
                "parentPR": parent_number,
                "parentTitle": parent_pr.get("title", ""),
                "parentBranch": parent_pr.get("headRefName", ""),
                "derivatives": [derivative["number"]],
            }

    return list(parents.values())


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def discover_and_classify(owner: str, repo: str, max_prs: int) -> dict[str, Any]:
    """Fetch open PRs, classify them, and detect derivatives.

    Returns a dict with keys: total_prs, action_required, blocked,
    derivative_prs, errors.
    """
    action_required: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    derivative_prs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    prs = get_open_prs(owner, repo, max_prs)
    total_prs = len(prs)

    logger.info("Found %d open PRs", total_prs)

    derivatives = get_derivative_prs(prs)
    if derivatives:
        derivative_prs.extend(derivatives)
        parents = get_parents_with_derivatives(prs, derivatives)
        for parent in parents:
            action_required.append(
                {
                    "number": parent["parentPR"],
                    "category": "has-derivatives",
                    "hasConflicts": False,
                    "hasFailingChecks": False,
                    "reason": "PENDING_DERIVATIVES",
                    "author": "N/A",
                    "title": parent["parentTitle"],
                    "headRefName": parent["parentBranch"],
                    "baseRefName": "",
                    "derivatives": parent["derivatives"],
                }
            )

    for pr in prs:
        try:
            author_login = (pr.get("author") or {}).get("login", "unknown")
            bot_info = classify_bot(author_login)
            is_agent_controlled = bot_info["is_bot"] and bot_info["category"] == "agent-controlled"
            is_mention_triggered = (
                bot_info["is_bot"] and bot_info["category"] == "mention-triggered"
            )
            is_bot_reviewer = has_bot_reviewer(pr.get("reviewRequests"))
            pr_has_changes_requested = pr.get("reviewDecision") == "CHANGES_REQUESTED"
            pr_has_conflicts = has_conflicts(pr)
            pr_has_failing = has_failing_checks(pr)
            pr_has_unresolved = has_unresolved_threads(pr)

            needs_action = (
                pr_has_changes_requested
                or pr_has_conflicts
                or pr_has_failing
                or pr_has_unresolved
            )
            if not needs_action:
                continue

            # Determine reason with priority: conflicts > failing > changes > unresolved
            if pr_has_conflicts:
                reason = "HAS_CONFLICTS"
            elif pr_has_failing:
                reason = "HAS_FAILING_CHECKS"
            elif pr_has_changes_requested:
                reason = "CHANGES_REQUESTED"
            else:
                reason = "HAS_UNRESOLVED_THREADS"

            pr_entry = {
                "number": pr["number"],
                "hasConflicts": pr_has_conflicts,
                "hasFailingChecks": pr_has_failing,
                "hasUnresolvedThreads": pr_has_unresolved,
                "reason": reason,
                "author": author_login,
                "title": pr.get("title", ""),
                "headRefName": pr.get("headRefName", ""),
                "baseRefName": pr.get("baseRefName", ""),
            }

            # Priority 1: Agent-controlled bot as author or reviewer
            if is_agent_controlled or is_bot_reviewer:
                pr_entry["category"] = "agent-controlled"
                action_required.append(pr_entry)
            # Priority 2: Mention-triggered bot
            elif is_mention_triggered:
                pr_entry["category"] = "mention-triggered"
                pr_entry["requiresSynthesis"] = True
                action_required.append(pr_entry)
            # Priority 3: Human-authored (blocked)
            else:
                pr_entry["category"] = "human-blocked"
                blocked.append(pr_entry)

        except Exception as exc:
            logger.exception("Error classifying PR #%s", pr.get("number"))
            errors.append({"PR": pr.get("number"), "error": str(exc)})

    return {
        "total_prs": total_prs,
        "action_required": action_required,
        "blocked": blocked,
        "derivative_prs": derivative_prs,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Summary output (non-JSON mode)
# ---------------------------------------------------------------------------


def _print_summary(results: dict[str, Any]) -> None:
    """Print a human-readable summary to stderr."""
    total = results["total_prs"]
    action = results["action_required"]
    blocked_list = results["blocked"]
    derivatives = results["derivative_prs"]
    errors = results["errors"]

    print("=== PR Discovery Summary ===", file=sys.stderr)
    print(f"Open PRs: {total}", file=sys.stderr)
    print(f"Action Required: {len(action)}", file=sys.stderr)
    print(f"Blocked (human): {len(blocked_list)}", file=sys.stderr)
    print(f"Derivatives: {len(derivatives)}", file=sys.stderr)

    if action:
        print("---", file=sys.stderr)
        print("PRs Requiring Action:", file=sys.stderr)
        for item in action:
            print(
                f"  PR #{item['number']}: {item['reason']} [{item['category']}]",
                file=sys.stderr,
            )
            if item.get("hasConflicts"):
                print(
                    "    -> Has conflicts, run /merge-resolver first",
                    file=sys.stderr,
                )
            if item.get("hasUnresolvedThreads"):
                print(
                    "    -> Has unresolved review threads, run /pr-review",
                    file=sys.stderr,
                )

    if blocked_list:
        print("---", file=sys.stderr)
        print("Blocked PRs (require human action):", file=sys.stderr)
        for item in blocked_list:
            print(
                f"  PR #{item['number']}: {item['reason']} - {item['title']}",
                file=sys.stderr,
            )

    if errors:
        print(f"Errors: {len(errors)}", file=sys.stderr)


def _write_step_summary(results: dict[str, Any]) -> None:
    """Write GitHub Actions step summary if GITHUB_STEP_SUMMARY is set."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    action = results["action_required"]
    blocked_list = results["blocked"]
    derivatives = results["derivative_prs"]

    lines = [
        "## PR Discovery Summary",
        "",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Open PRs Scanned | {results['total_prs']} |",
        f"| PRs Need Action | {len(action)} |",
        f"| Blocked (human) | {len(blocked_list)} |",
        f"| Derivative PRs | {len(derivatives)} |",
        f"| Errors | {len(results['errors'])} |",
        "",
    ]

    if action:
        lines.extend(
            [
                "### PRs Requiring Action",
                "",
                "| PR | Category | Reason | Has Conflicts | Unresolved Threads |",
                "|----|----------|--------|---------------|-------------------|",
            ]
        )
        for item in action:
            has_conflicts = item.get("hasConflicts")
            has_threads = item.get("hasUnresolvedThreads")
            conflict_icon = ":warning:" if has_conflicts else ":white_check_mark:"
            thread_icon = ":speech_balloon:" if has_threads else ":white_check_mark:"
            lines.append(
                f"| #{item['number']} | {item['category']} | {item['reason']} "
                f"| {conflict_icon} | {thread_icon} |"
            )
        lines.append("")

    if blocked_list:
        lines.extend(
            [
                "### Blocked PRs (Human Action Required)",
                "",
                "| PR | Author | Reason |",
                "|----|--------|--------|",
            ]
        )
        for item in blocked_list:
            lines.append(f"| #{item['number']} | {item['author']} | {item['reason']} |")

    with open(summary_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PR discovery and classification for GitHub Actions matrix strategy."
    )
    parser.add_argument(
        "--owner",
        default="",
        help="Repository owner (inferred from git remote if omitted)",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="Repository name (inferred from git remote if omitted)",
    )
    parser.add_argument(
        "--max-prs",
        type=int,
        default=20,
        help="Maximum PRs to process (default: 20)",
    )
    parser.add_argument(
        "--log-path",
        default="",
        help="Path to write detailed log file",
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output JSON to stdout for matrix consumption",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.output_json:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            stream=sys.stderr,
        )

    # Check rate limit (fail-safe: exit 0 if too low, not 2)
    try:
        rate_result = check_workflow_rate_limit(resource_thresholds={"core": 100, "graphql": 50})
        if rate_result.status != RateLimitStatus.VERIFIED_HEALTHY:
            if not args.output_json:
                reason = rate_result.probe_error or "thresholds not met"
                status = rate_result.status.value
                print(f"Exiting: API rate limit gate {status} ({reason})", file=sys.stderr)
            return 0
    except RuntimeError:
        if not args.output_json:
            logger.exception("Failed to check rate limit")
        print("Cannot verify API rate limit. Aborting.", file=sys.stderr)
        return 0

    try:
        repo_params = resolve_repo_params(args.owner, args.repo)
    except SystemExit:
        raise
    except Exception:
        print("Failed to resolve repository parameters.", file=sys.stderr)
        return 2

    owner = repo_params.owner
    repo = repo_params.repo

    results = discover_and_classify(owner, repo, args.max_prs)

    if args.output_json:
        # Sort: conflicts first, then failing checks, then by number
        sorted_prs = sorted(
            results["action_required"],
            key=lambda pr: (
                not pr.get("hasConflicts", False),
                not pr.get("hasFailingChecks", False),
                pr.get("number", 0),
            ),
        )

        output = {
            "prs": sorted_prs,
            "summary": {
                "total": results["total_prs"],
                "actionRequired": len(results["action_required"]),
                "blocked": len(results["blocked"]),
                "derivatives": len(results["derivative_prs"]),
            },
        }
        print(json.dumps(output, separators=(",", ":")))
        return 0

    _print_summary(results)
    _write_step_summary(results)

    if args.log_path:
        logger.info("Log path requested but logging is to stderr in Python mode")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
