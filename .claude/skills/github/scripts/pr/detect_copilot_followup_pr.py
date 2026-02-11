#!/usr/bin/env python3
"""Detect and analyze Copilot follow-up PR patterns.

Identifies when Copilot creates follow-up PRs after PR comment replies.
Categorizes follow-ups as DUPLICATE, SUPPLEMENTAL, or INDEPENDENT.
Returns structured data for decision-making.

Pattern: Copilot creates PR with branch copilot/sub-pr-{original_pr}
targeting the original PR's base branch.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime

_WORKSPACE = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
    ),
)
sys.path.insert(0, _WORKSPACE)

from scripts.github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)

# ---------------------------------------------------------------------------
# Pattern matching
# ---------------------------------------------------------------------------

# End-of-string anchor prevents matching branches with non-numeric suffixes
_FOLLOWUP_BRANCH_PATTERN = re.compile(r"copilot/sub-pr-(\d+)$")
# Multiline mode for diff section splitting
_DIFF_FILE_PATTERN = re.compile(r"(?m)^[ \t]*a/([^\r\n]+?)[ \t]+b/")


def test_followup_pattern(pr: dict, original_pr_number: int = 0) -> bool:
    """Check if a PR matches the Copilot follow-up branch pattern."""
    head_ref = pr.get("headRefName", "")
    match = _FOLLOWUP_BRANCH_PATTERN.search(head_ref)
    if not match:
        return False
    if original_pr_number > 0:
        return int(match.group(1)) == original_pr_number
    return True


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def get_copilot_announcement(
    owner: str, repo: str, pr_number: int,
) -> str | None:
    """Find Copilot's announcement comment on the original PR."""
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/issues/{pr_number}/comments",
            "--jq",
            '.[] | select(.user.login == "copilot-swe-agent[bot]" and '
            '(.body | contains("opened a new pull request"))) | '
            '{id: .id, body: .body, created_at: .created_at}',
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def get_followup_pr_diff(
    owner: str, repo: str, followup_pr_number: int,
) -> str:
    """Get unified diff for a follow-up PR."""
    result = subprocess.run(
        ["gh", "pr", "diff", str(followup_pr_number), "--repo", f"{owner}/{repo}"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def get_original_pr_commits(
    owner: str, repo: str, pr_number: int,
) -> list[dict]:
    """Get commits from original PR for comparison."""
    result = subprocess.run(
        [
            "gh", "pr", "view", str(pr_number),
            "--repo", f"{owner}/{repo}",
            "--json", "commits",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        pr_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    commits: list[dict] = pr_data.get("commits", [])
    return commits


# ---------------------------------------------------------------------------
# Diff comparison
# ---------------------------------------------------------------------------


def compare_diff_content(
    owner: str,
    repo: str,
    followup_diff: str,
    original_commits: list[dict],
    original_pr_number: int = 0,
) -> dict:
    """Compare follow-up diff to original changes. Returns analysis dict."""
    if not followup_diff or not followup_diff.strip():
        reason = "Follow-up PR contains no changes"

        if original_pr_number > 0:
            result = subprocess.run(
                [
                    "gh", "pr", "view", str(original_pr_number),
                    "--repo", f"{owner}/{repo}",
                    "--json", "merged",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    merge_data = json.loads(result.stdout)
                    if merge_data.get("merged"):
                        reason = "Follow-up contains no changes (original PR already merged)"
                except json.JSONDecodeError:
                    pass

        return {"similarity": 100, "category": "DUPLICATE", "reason": reason}

    # Extract file paths from follow-up diff
    diff_sections = [
        s for s in re.split(r"(?m)^diff --git", followup_diff)
        if s.strip()
    ]
    followup_files: list[str] = []
    for section in diff_sections:
        match = _DIFF_FILE_PATTERN.search(section)
        if match:
            followup_files.append(match.group(1))

    # Extract file paths from original commits
    original_files: list[str] = []
    for commit in original_commits:
        changed = commit.get("changedFiles", [])
        if isinstance(changed, list):
            original_files.extend(changed)
        elif isinstance(changed, str):
            original_files.append(changed)
    original_files = list(set(original_files))

    # Calculate file overlap
    overlap_count = sum(1 for f in followup_files if f in original_files)

    overlap_pct = 0
    if followup_files:
        overlap_pct = round((overlap_count / len(followup_files)) * 100)

    # Determine category
    if not followup_files:
        if diff_sections:
            return {
                "similarity": 0,
                "category": "UNKNOWN",
                "reason": (
                    f"File extraction failed from diff "
                    f"({len(diff_sections)} sections, 0 files extracted)"
                ),
            }
        return {
            "similarity": 100,
            "category": "DUPLICATE",
            "reason": "No file changes detected in follow-up diff",
        }

    if overlap_pct >= 80:
        return {
            "similarity": overlap_pct,
            "category": "DUPLICATE",
            "reason": (
                f"High file overlap ({overlap_count} of "
                f"{len(followup_files)} files match original PR)"
            ),
        }

    if overlap_pct >= 50 or (len(followup_files) == 1 and original_commits):
        if overlap_pct >= 50:
            reason = (
                f"Partial file overlap ({overlap_count} of "
                f"{len(followup_files)} files match original PR)"
            )
        else:
            reason = (
                "Single file change with original commits present "
                "(heuristic: likely addressing review feedback)"
            )
        return {
            "similarity": max(85, overlap_pct),
            "category": "LIKELY_DUPLICATE",
            "reason": reason,
        }

    if overlap_pct > 0:
        return {
            "similarity": overlap_pct,
            "category": "POSSIBLE_SUPPLEMENTAL",
            "reason": (
                f"Some file overlap ({overlap_count} of "
                f"{len(followup_files)} files), may extend original work"
            ),
        }

    return {
        "similarity": 0,
        "category": "INDEPENDENT",
        "reason": (
            f"No file overlap with original PR "
            f"({len(followup_files)} new files)"
        ),
    }


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_followups(
    owner: str, repo: str, pr_number: int,
) -> dict:
    """Main detection logic. Returns structured result."""
    # Step 1: Query for follow-up PRs
    search_query = f"head:copilot/sub-pr-{pr_number}"
    result = subprocess.run(
        [
            "gh", "pr", "list",
            "--repo", f"{owner}/{repo}",
            "--state", "open",
            "--search", search_query,
            "--json", "number,title,body,headRefName,baseRefName,state,author,createdAt",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    followup_prs: list[dict] = []
    if result.returncode == 0 and result.stdout.strip():
        try:
            pr_data = json.loads(result.stdout)
            if isinstance(pr_data, list):
                followup_prs = pr_data
            elif pr_data is not None:
                followup_prs = [pr_data]
        except json.JSONDecodeError:
            pass

    # Filter with pattern validation
    followup_prs = [
        p for p in followup_prs
        if test_followup_pattern(p, pr_number)
    ]

    if not followup_prs:
        return {
            "found": False,
            "followUpPRs": [],
            "announcement": None,
            "analysis": None,
            "recommendation": "NO_ACTION_NEEDED",
            "message": "No follow-up PRs detected",
        }

    # Step 2: Verify Copilot announcement
    announcement = get_copilot_announcement(owner, repo, pr_number)
    if not announcement:
        print(
            "WARNING: No Copilot announcement found, but follow-up PR exists",
            file=sys.stderr,
        )

    # Step 3: Analyze each follow-up PR
    analyses: list[dict] = []
    for followup in followup_prs:
        fu_num = followup["number"]
        diff = get_followup_pr_diff(owner, repo, fu_num)
        original_commits = get_original_pr_commits(owner, repo, pr_number)

        comparison = compare_diff_content(
            owner, repo, diff, original_commits, pr_number,
        )

        # Determine recommendation
        category = comparison["category"]
        recommendation_map = {
            "DUPLICATE": "CLOSE_AS_DUPLICATE",
            "LIKELY_DUPLICATE": "REVIEW_THEN_CLOSE",
            "POSSIBLE_SUPPLEMENTAL": "EVALUATE_FOR_MERGE",
            "INDEPENDENT": "EVALUATE_FOR_MERGE",
        }
        recommendation = recommendation_map.get(category, "MANUAL_REVIEW")

        author_login = ""
        author_data = followup.get("author")
        if isinstance(author_data, dict):
            author_login = author_data.get("login", "")

        analyses.append({
            "followUpPRNumber": fu_num,
            "headBranch": followup.get("headRefName", ""),
            "baseBranch": followup.get("baseRefName", ""),
            "createdAt": followup.get("createdAt", ""),
            "author": author_login,
            "category": category,
            "similarity": comparison["similarity"],
            "reason": comparison["reason"],
            "recommendation": recommendation,
        })

    overall_rec = (
        analyses[0]["recommendation"]
        if len(analyses) == 1
        else "MULTIPLE_FOLLOW_UPS_REVIEW"
    )

    return {
        "found": True,
        "originalPRNumber": pr_number,
        "followUpPRs": followup_prs,
        "announcement": announcement,
        "analysis": analyses,
        "recommendation": overall_rec,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect and analyze Copilot follow-up PR patterns.",
    )
    parser.add_argument(
        "--pr-number", type=int, required=True,
        help="Original PR number to check for follow-ups",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved["Owner"]
    repo = resolved["Repo"]

    result = detect_followups(owner, repo, args.pr_number)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
