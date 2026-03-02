#!/usr/bin/env python3
"""Assign a milestone to a GitHub Issue.

Manages milestone assignment:
- Validates milestone exists before assigning
- Supports clearing existing milestone
- Supports force-replacing existing milestone

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = Milestone not found
    3 = API error
    4 = Not authenticated
    5 = Has milestone (use --force)
"""

import argparse
import json
import os
import subprocess
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


def _get_current_milestone(owner: str, repo: str, issue: int) -> str | None:
    """Get the current milestone title for an issue."""
    result = _run_gh(
        "api", f"repos/{owner}/{repo}/issues/{issue}",
        "--jq", ".milestone.title",
        check=False,
    )
    if result.returncode != 0:
        return None
    title = result.stdout.strip()
    if not title or title == "null":
        return None
    return title


def _list_milestone_titles(owner: str, repo: str) -> list[str]:
    """List all open milestone titles."""
    result = _run_gh(
        "api", f"repos/{owner}/{repo}/milestones",
        "--jq", ".[].title",
        check=False,
    )
    if result.returncode != 0:
        return []
    return [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]


def set_issue_milestone(
    owner: str,
    repo: str,
    issue: int,
    milestone: str = "",
    clear: bool = False,
    force: bool = False,
) -> dict:
    """Assign or clear a milestone on a GitHub issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue: Issue number.
        milestone: Milestone title to assign.
        clear: Clear existing milestone.
        force: Replace existing milestone.

    Returns:
        Dict with operation result.
    """
    current = _get_current_milestone(owner, repo, issue)

    output = {
        "Success": False,
        "Issue": issue,
        "Milestone": None,
        "PreviousMilestone": current,
        "Action": "none",
    }

    if clear:
        if not current:
            output["Success"] = True
            output["Action"] = "no_change"
            return output

        result = subprocess.run(
            [
                "gh", "api", f"repos/{owner}/{repo}/issues/{issue}",
                "-X", "PATCH", "-f", "milestone=",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            write_error_and_exit("Failed to clear milestone", 3)

        output["Success"] = True
        output["Action"] = "cleared"
        return output

    # Check milestone exists
    titles = _list_milestone_titles(owner, repo)
    if milestone not in titles:
        write_error_and_exit(
            f"Milestone '{milestone}' does not exist in {owner}/{repo}.", 2
        )

    # Already assigned
    if current == milestone:
        output["Success"] = True
        output["Milestone"] = milestone
        output["Action"] = "no_change"
        return output

    # Has different milestone without force
    if current and not force:
        write_error_and_exit(
            f"Issue #{issue} already has milestone '{current}'. "
            f"Use --force to override.", 5
        )

    # Assign
    result = subprocess.run(
        [
            "gh", "issue", "edit", str(issue),
            "--repo", f"{owner}/{repo}",
            "--milestone", milestone,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        write_error_and_exit("Failed to set milestone", 3)

    action = "replaced" if current else "assigned"
    output["Success"] = True
    output["Milestone"] = milestone
    output["Action"] = action
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign or clear a milestone on a GitHub issue"
    )
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument("--milestone", help="Milestone title to assign")
    parser.add_argument(
        "--clear", action="store_true",
        help="Clear existing milestone",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Replace existing milestone",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    if not args.clear and not args.milestone:
        write_error_and_exit(
            "Either --milestone or --clear is required.", 1
        )

    output = set_issue_milestone(
        resolved["owner"], resolved["repo"], args.issue,
        milestone=args.milestone or "",
        clear=args.clear,
        force=args.force,
    )

    print(json.dumps(output, indent=2))
    action = output["Action"]
    ms = output.get("Milestone", "")
    if action == "assigned":
        print(
            f"Set milestone '{ms}' on issue #{args.issue}",
            file=sys.stderr,
        )
    elif action == "replaced":
        prev = output.get("PreviousMilestone", "")
        print(
            f"Replaced milestone '{prev}' with '{ms}' on issue #{args.issue}",
            file=sys.stderr,
        )
    elif action == "cleared":
        print(f"Cleared milestone from issue #{args.issue}", file=sys.stderr)
    elif action == "no_change":
        print(f"Issue #{args.issue} already up to date.", file=sys.stderr)


if __name__ == "__main__":
    main()
