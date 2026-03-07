#!/usr/bin/env python3
"""Assign a milestone to a GitHub PR or issue.

Exit codes follow ADR-035:
    0 - Success (assigned or skipped)
    2 - Config error (no milestone found, detection failed)
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import write_github_output, write_step_summary  # noqa: E402
from scripts.github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    gh_api_paginated,
    resolve_repo_params,
)

# Matches semantic version strings like "0.2.0", "1.10.3"
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


# -------------------------------------------------------------------
# Milestone detection
# -------------------------------------------------------------------


def _parse_semver_tuple(version: str) -> tuple[int, ...]:
    """Parse "X.Y.Z" into (X, Y, Z) for proper numeric sorting."""
    return tuple(int(part) for part in version.split("."))


def get_latest_semantic_milestone(
    owner: str,
    repo: str,
) -> dict[str, object]:
    """Detect the latest open semantic version milestone.

    Returns dict with keys: title (str), number (int), found (bool).
    Raises SystemExit on API errors (exit code 3).
    """
    endpoint = f"repos/{owner}/{repo}/milestones?state=open"
    milestones = gh_api_paginated(endpoint)

    if not milestones:
        return {"title": "", "number": 0, "found": False}

    semantic = [m for m in milestones if _SEMVER_PATTERN.match(m.get("title", ""))]

    if not semantic:
        available = ", ".join(m.get("title", "(untitled)") for m in milestones)
        print(
            f"No semantic version milestones found. Available: {available}",
            file=sys.stderr,
        )
        return {"title": "", "number": 0, "found": False}

    latest = max(semantic, key=lambda m: _parse_semver_tuple(m["title"]))

    return {
        "title": latest["title"],
        "number": latest["number"],
        "found": True,
    }


# -------------------------------------------------------------------
# Item milestone queries
# -------------------------------------------------------------------


def get_item_milestone(
    owner: str,
    repo: str,
    number: int,
) -> str | None:
    """Return the current milestone title for a PR/issue, or None."""
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/issues/{number}"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        error_and_exit(
            f"Failed to query item #{number}: {error_str}",
            3,
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        error_and_exit(f"Invalid JSON from item #{number}: {exc}", 3)

    milestone = data.get("milestone")
    if milestone and milestone.get("title"):
        return str(milestone["title"])
    return None


# -------------------------------------------------------------------
# Milestone assignment
# -------------------------------------------------------------------


def assign_milestone(
    owner: str,
    repo: str,
    number: int,
    milestone_title: str,
) -> None:
    """Assign a milestone to a PR/issue via gh CLI.

    Raises SystemExit on failure (exit code 3).
    """
    result = subprocess.run(
        [
            "gh",
            "issue",
            "edit",
            str(number),
            "--repo",
            f"{owner}/{repo}",
            "--milestone",
            milestone_title,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        error_and_exit(
            f"Failed to assign milestone '{milestone_title}' to #{number}: {error_str}",
            3,
        )


# -------------------------------------------------------------------
# Output summary
# -------------------------------------------------------------------


def _write_result(
    success: bool,
    item_type: str,
    item_number: int,
    milestone: str,
    action: str,
    message: str,
) -> None:
    """Write result to GITHUB_OUTPUT and GITHUB_STEP_SUMMARY."""
    write_github_output(
        {
            "success": str(success).lower(),
            "item_type": item_type,
            "item_number": str(item_number),
            "milestone": milestone,
            "action": action,
            "message": message,
        }
    )

    icon = "+" if success else "X"
    item_label = "Pull Request" if item_type == "pr" else "Issue"
    summary = (
        f"## Milestone Assignment Result\n\n"
        f"**Status**: {icon} {action.upper()}\n\n"
        f"**{item_label}**: #{item_number}\n"
        f"**Milestone**: {milestone}\n\n"
        f"{message}\n"
    )
    write_step_summary(summary)


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Assign a milestone to a GitHub PR or issue. "
            "Auto-detects latest semantic version milestone if "
            "--milestone-title is not provided."
        ),
    )
    parser.add_argument(
        "--item-type",
        required=True,
        choices=["pr", "issue"],
        help="Type of item: pr or issue",
    )
    parser.add_argument(
        "--item-number",
        type=int,
        required=True,
        help="PR or issue number",
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
        "--milestone-title",
        default="",
        help="Specific milestone to assign (auto-detects if omitted)",
    )
    return parser


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code per ADR-035."""
    parser = build_parser()
    args = parser.parse_args(argv)

    item_type: str = args.item_type
    item_number: int = args.item_number

    # Authenticate
    assert_gh_authenticated()

    # Resolve owner/repo
    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    # Check current milestone
    existing = get_item_milestone(owner, repo, item_number)
    if existing:
        msg = (
            f"Already has milestone '{existing}'. No action taken (preserving manual assignments)."
        )
        print(f"{item_type} #{item_number} already has milestone: {existing}")
        _write_result(True, item_type, item_number, existing, "skipped", msg)
        return 0

    # Determine milestone to assign
    milestone_title: str = args.milestone_title
    if not milestone_title:
        detection = get_latest_semantic_milestone(owner, repo)
        if not detection["found"]:
            msg = (
                "No semantic version milestone found. "
                "Create one (e.g., 0.3.0) or pass --milestone-title."
            )
            print(msg, file=sys.stderr)
            _write_result(
                False,
                item_type,
                item_number,
                "",
                "failed",
                msg,
            )
            return 2
        milestone_title = str(detection["title"])

    # Assign
    print(f"Assigning milestone '{milestone_title}' to {item_type} #{item_number}")
    assign_milestone(owner, repo, item_number, milestone_title)

    msg = f"Assigned milestone '{milestone_title}'."
    print(f"Successfully assigned milestone '{milestone_title}' to {item_type} #{item_number}")
    _write_result(True, item_type, item_number, milestone_title, "assigned", msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
