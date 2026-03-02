#!/usr/bin/env python3
"""Assign milestone to PR or issue if none exists.

Orchestrates milestone assignment for GitHub PRs and issues:
1. Checks if item already has a milestone (skips if present)
2. Auto-detects latest semantic version milestone (unless --milestone-title provided)
3. Assigns the milestone

Exit codes (ADR-035):
    0 = Success (milestone assigned or skipped)
    1 = Invalid parameters
    2 = Milestone not found / detection failed
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
    _run_gh,
    assert_gh_authenticated,
    resolve_repo_params,
    write_error_and_exit,
)

# Import sibling scripts for delegation
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_issue_dir = os.path.join(os.path.dirname(_scripts_dir), "issue")


def _get_item_milestone(
    owner: str, repo: str, item_number: int,
) -> str | None:
    """Check if a PR/issue already has a milestone."""
    result = _run_gh(
        "api", f"repos/{owner}/{repo}/issues/{item_number}",
        check=False,
    )
    if result.returncode != 0:
        write_error_and_exit(
            f"Failed to query item #{item_number}: {result.stderr}", 3
        )

    data = json.loads(result.stdout)
    milestone = data.get("milestone")
    if milestone and milestone.get("title", "").strip():
        return milestone["title"]
    return None


def set_item_milestone(
    owner: str,
    repo: str,
    item_type: str,
    item_number: int,
    milestone_title: str = "",
) -> dict:
    """Assign a milestone to a PR or issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        item_type: "pr" or "issue".
        item_number: PR or issue number.
        milestone_title: Specific milestone. Auto-detects if empty.

    Returns:
        Dict with operation result.
    """
    # Check existing milestone
    existing = _get_item_milestone(owner, repo, item_number)
    if existing:
        return {
            "Success": True,
            "ItemType": item_type,
            "ItemNumber": item_number,
            "Milestone": existing,
            "Action": "skipped",
            "Message": (
                f"Already has milestone '{existing}'. "
                f"No action taken (preserving manual assignments)."
            ),
        }

    # Auto-detect milestone if not provided
    if not milestone_title:
        # Import get_latest_semantic_milestone from sibling module
        from milestone.get_latest_semantic_milestone import (
            get_latest_semantic_milestone,
        )
        detection = get_latest_semantic_milestone(owner, repo)
        if not detection.get("Found"):
            write_error_and_exit(
                "Failed to detect latest semantic milestone. "
                "Create a semantic version milestone (e.g., 0.2.0) "
                "or specify --milestone-title.", 2
            )
        milestone_title = detection["Title"]

    # Assign milestone (GitHub treats PRs as issues for milestone API)
    import subprocess
    result = subprocess.run(
        [
            "gh", "issue", "edit", str(item_number),
            "--repo", f"{owner}/{repo}",
            "--milestone", milestone_title,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        write_error_and_exit(
            f"Failed to assign milestone: {result.stderr}", 3
        )

    return {
        "Success": True,
        "ItemType": item_type,
        "ItemNumber": item_number,
        "Milestone": milestone_title,
        "Action": "assigned",
        "Message": (
            f"Assigned milestone '{milestone_title}' "
            f"(auto-detected latest semantic version)."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign milestone to PR or issue if none exists"
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument(
        "--item-type", required=True, choices=["pr", "issue"],
        help="Type of item",
    )
    parser.add_argument(
        "--item-number", type=int, required=True,
        help="PR or issue number",
    )
    parser.add_argument(
        "--milestone-title", default="",
        help="Specific milestone to assign (auto-detects if empty)",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    # Add milestone scripts dir to path for cross-import
    milestone_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if milestone_parent not in sys.path:
        sys.path.insert(0, milestone_parent)

    output = set_item_milestone(
        resolved["owner"], resolved["repo"],
        args.item_type, args.item_number,
        args.milestone_title,
    )

    print(json.dumps(output, indent=2))
    action = output["Action"]
    ms = output.get("Milestone", "")
    print(
        f"{args.item_type} #{args.item_number}: {action} ({ms})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
