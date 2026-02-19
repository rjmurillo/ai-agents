#!/usr/bin/env python3
"""PR discovery and classification for GitHub Actions matrix strategy.

THIN ORCHESTRATION LAYER: Identifies PRs needing attention and outputs JSON
for GitHub Actions matrix to spawn parallel pr-comment-responder jobs.

This script ONLY does:
- Discover open PRs
- Classify each PR by activation trigger
- Detect conflicts and derivative PRs
- Output ActionRequired JSON for workflow matrix

EXIT CODES:
  0  - Success: PR maintenance completed
  2  - Error: Script failure, API errors, or fatal exceptions

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.github_core import check_workflow_rate_limit, resolve_repo_params

logger = logging.getLogger(__name__)

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


def run_gh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)


@dataclass
class BotInfo:
    is_bot: bool
    category: str
    name: str


def get_bot_author_info(author_login: str) -> BotInfo:
    for category, bots in BOT_CATEGORIES.items():
        for bot in bots:
            if author_login.lower() == bot.lower() or author_login.lower().startswith(
                bot.lower()
            ):
                return BotInfo(is_bot=True, category=category, name=author_login)
    return BotInfo(is_bot=False, category="human", name=author_login)


def is_bot_reviewer(review_requests: dict[str, Any] | None) -> bool:
    if not review_requests or "nodes" not in review_requests:
        return False
    for request in review_requests["nodes"]:
        reviewer = request.get("requestedReviewer")
        if not reviewer:
            continue
        login = reviewer.get("login", "")
        if not login:
            continue
        bot_info = get_bot_author_info(login)
        if bot_info.is_bot and bot_info.category == "agent-controlled":
            return True
    return False


def has_failing_checks(pr: dict[str, Any]) -> bool:
    commits = pr.get("commits", {})
    nodes = commits.get("nodes", [])
    if not nodes:
        return False

    commit = nodes[0].get("commit", {})
    rollup = commit.get("statusCheckRollup")
    if not rollup:
        return False

    state = rollup.get("state", "")
    if state in ("FAILURE", "ERROR"):
        return True

    contexts = rollup.get("contexts", {})
    context_nodes = contexts.get("nodes", [])
    for ctx in context_nodes:
        if ctx.get("conclusion") == "FAILURE" or ctx.get("state") == "FAILURE":
            return True

    return False


GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $limit: Int!) {
    repository(owner: $owner, name: $name) {
        pullRequests(first: $limit, states: OPEN,
                     orderBy: {field: UPDATED_AT, direction: DESC}) {
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
                commits(last: 1) {
                    nodes {
                        commit {
                            statusCheckRollup {
                                state
                                contexts(first: 100) {
                                    nodes {
                                        ... on CheckRun {
                                            name
                                            conclusion
                                            status
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
}
"""


def get_open_prs(owner: str, repo: str, limit: int) -> list[dict[str, Any]]:
    result = run_gh(
        "api",
        "graphql",
        "-f",
        f"query={GRAPHQL_QUERY}",
        "-f",
        f"owner={owner}",
        "-f",
        f"name={repo}",
        "-F",
        f"limit={limit}",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to query PRs: {result.stderr}")
    try:
        data = json.loads(result.stdout)
        nodes: list[dict[str, Any]] = data["data"]["repository"]["pullRequests"]["nodes"]
        return nodes
    except (json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(
            f"Failed to parse PR response: {exc}"
        ) from exc


@dataclass
class MaintenanceResults:
    total_prs: int = 0
    action_required: list[dict[str, Any]] = field(default_factory=list)
    blocked: list[dict[str, Any]] = field(default_factory=list)
    derivative_prs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def classify_prs(
    owner: str, repo: str, prs: list[dict[str, Any]],
) -> MaintenanceResults:
    results = MaintenanceResults(total_prs=len(prs))

    # Detect derivative PRs
    for pr in prs:
        if pr.get("baseRefName") not in PROTECTED_BRANCHES:
            results.derivative_prs.append(
                {
                    "number": pr["number"],
                    "title": pr.get("title", ""),
                    "author": pr.get("author", {}).get("login", ""),
                    "targetBranch": pr.get("baseRefName", ""),
                    "sourceBranch": pr.get("headRefName", ""),
                }
            )

    # Find parents with derivatives
    for derivative in results.derivative_prs:
        parent = next(
            (p for p in prs if p.get("headRefName") == derivative["targetBranch"]),
            None,
        )
        if parent:
            results.action_required.append(
                {
                    "number": parent["number"],
                    "category": "has-derivatives",
                    "hasConflicts": False,
                    "reason": "PENDING_DERIVATIVES",
                    "author": "N/A",
                    "title": parent.get("title", ""),
                }
            )

    for pr in prs:
        try:
            author_login = pr.get("author", {}).get("login", "")
            bot_info = get_bot_author_info(author_login)
            is_agent = bot_info.is_bot and bot_info.category == "agent-controlled"
            is_mention = bot_info.is_bot and bot_info.category == "mention-triggered"
            is_reviewer = is_bot_reviewer(pr.get("reviewRequests"))
            has_changes = pr.get("reviewDecision") == "CHANGES_REQUESTED"
            has_conflicts = pr.get("mergeable") == "CONFLICTING"
            has_failures = has_failing_checks(pr)

            needs_action = has_changes or has_conflicts or has_failures
            if not needs_action:
                continue

            if has_changes:
                reason = "CHANGES_REQUESTED"
            elif has_conflicts:
                reason = "HAS_CONFLICTS"
            else:
                reason = "HAS_FAILING_CHECKS"

            if is_agent or is_reviewer:
                results.action_required.append(
                    {
                        "number": pr["number"],
                        "category": "agent-controlled",
                        "hasConflicts": has_conflicts,
                        "hasFailingChecks": has_failures,
                        "reason": reason,
                        "author": author_login,
                        "title": pr.get("title", ""),
                        "headRefName": pr.get("headRefName", ""),
                        "baseRefName": pr.get("baseRefName", ""),
                    }
                )
            elif is_mention:
                results.action_required.append(
                    {
                        "number": pr["number"],
                        "category": "mention-triggered",
                        "hasConflicts": has_conflicts,
                        "hasFailingChecks": has_failures,
                        "reason": reason,
                        "author": author_login,
                        "title": pr.get("title", ""),
                        "headRefName": pr.get("headRefName", ""),
                        "baseRefName": pr.get("baseRefName", ""),
                        "requiresSynthesis": True,
                    }
                )
            else:
                results.blocked.append(
                    {
                        "number": pr["number"],
                        "category": "human-blocked",
                        "hasConflicts": has_conflicts,
                        "hasFailingChecks": has_failures,
                        "reason": reason,
                        "author": author_login,
                        "title": pr.get("title", ""),
                    }
                )

        except KeyError as e:
            results.errors.append(
                {"PR": pr.get("number") or "Unknown", "Error": str(e)}
            )

    if results.errors:
        failed = ", ".join(
            f"#{e['PR']} (missing {e['Error']})" for e in results.errors
        )
        raise RuntimeError(
            f"Classification failed for PRs: {failed}"
        )

    return results


def print_summary(results: MaintenanceResults) -> None:
    print("---")
    print("=== PR Discovery Summary ===")
    print(f"Open PRs: {results.total_prs}")
    print(f"Action Required: {len(results.action_required)}")
    print(f"Blocked (human): {len(results.blocked)}")
    print(f"Derivatives: {len(results.derivative_prs)}")

    if results.action_required:
        print("---")
        print("PRs Requiring Action:")
        for item in results.action_required:
            print(f"  PR #{item['number']}: {item['reason']} [{item['category']}]")
            if item.get("hasConflicts"):
                print("    -> Has conflicts, run /merge-resolver first")

        pr_numbers = ",".join(str(item["number"]) for item in results.action_required)
        print(f"Run: /pr-comment-responder {pr_numbers}")

    if results.blocked:
        print("---")
        print("Blocked PRs (require human action):")
        for item in results.blocked:
            print(f"  PR #{item['number']}: {item['reason']} - {item['title']}")


def write_step_summary(results: MaintenanceResults) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    lines = [
        "## PR Discovery Summary\n",
        "| Metric | Count |",
        "|--------|-------|",
        f"| Open PRs Scanned | {results.total_prs} |",
        f"| PRs Need Action | {len(results.action_required)} |",
        f"| Blocked (human) | {len(results.blocked)} |",
        f"| Derivative PRs | {len(results.derivative_prs)} |",
        f"| Errors | {len(results.errors)} |",
        "",
    ]

    with Path(summary_path).open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PR discovery and classification"
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--max-prs", type=int, default=20, help="Max PRs to process")
    parser.add_argument("--log-path", default="", help="Path to write log file")
    parser.add_argument(
        "--output-json", action="store_true", help="Output JSON for matrix"
    )
    args = parser.parse_args(argv)

    # Rate limit check (fail-safe: exit 0 if too low or check fails)
    try:
        rate_result = check_workflow_rate_limit(
            resource_thresholds={"core": 100, "graphql": 50},
        )
        if not rate_result.success:
            if not args.output_json:
                print("Exiting: API rate limit too low", file=sys.stderr)
            return 0
    except (RuntimeError, subprocess.SubprocessError, OSError, KeyError):
        if not args.output_json:
            logger.exception("Failed to check rate limit")
        print("Cannot verify API rate limit. Aborting.", file=sys.stderr)
        return 0

    try:
        repo_params = resolve_repo_params(args.owner, args.repo)
    except SystemExit:
        # Convert to script's documented exit code (error_and_exit already printed message)
        return 2
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"Failed to resolve repository parameters: {exc}", file=sys.stderr)
        return 2

    owner = repo_params["Owner"]
    repo = repo_params["Repo"]

    try:
        prs = get_open_prs(owner, repo, args.max_prs)
        results = classify_prs(owner, repo, prs)

        if args.output_json:
            sorted_prs = sorted(
                results.action_required,
                key=lambda x: (
                    not x.get("hasConflicts", False),
                    not x.get("hasFailingChecks", False),
                    x.get("number", 0),
                ),
            )
            output = {
                "prs": sorted_prs,
                "summary": {
                    "total": results.total_prs,
                    "actionRequired": len(results.action_required),
                    "blocked": len(results.blocked),
                    "derivatives": len(results.derivative_prs),
                },
            }
            print(json.dumps(output, separators=(",", ":")))
            return 0

        print_summary(results)
        write_step_summary(results)
        return 0

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
