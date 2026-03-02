#!/usr/bin/env python3
"""Assign users to a GitHub Issue.

Manages assignees on GitHub Issues:
- Adds one or more assignees to an issue
- Supports @me shorthand for current authenticated user
- Validates assignees are valid GitHub usernames

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    3 = API error (any assignment failed)
    4 = Not authenticated
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
    assert_gh_authenticated,
    resolve_repo_params,
    write_error_and_exit,
)


def set_issue_assignee(
    owner: str, repo: str, issue: int, assignees: list[str],
) -> dict:
    """Assign users to an issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue: Issue number.
        assignees: List of GitHub usernames.

    Returns:
        Dict with assignment results.
    """
    if not assignees:
        return {
            "Success": True,
            "Issue": issue,
            "Applied": [],
            "Failed": [],
            "TotalApplied": 0,
        }

    applied = []
    failed = []

    for assignee in assignees:
        result = subprocess.run(
            [
                "gh", "issue", "edit", str(issue),
                "--repo", f"{owner}/{repo}",
                "--add-assignee", assignee,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            applied.append(assignee)
        else:
            failed.append(assignee)

    return {
        "Success": len(failed) == 0,
        "Issue": issue,
        "Applied": applied,
        "Failed": failed,
        "TotalApplied": len(applied),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Assign users to a GitHub issue")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument(
        "--assignees", nargs="+", required=True,
        help="GitHub usernames to assign",
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    output = set_issue_assignee(
        resolved["owner"], resolved["repo"], args.issue, args.assignees,
    )

    print(json.dumps(output, indent=2))
    if output["Applied"]:
        names = ", ".join(output["Applied"])
        print(
            f"Assigned {output['TotalApplied']} user(s) to issue "
            f"#{args.issue}: {names}",
            file=sys.stderr,
        )
    if output["Failed"]:
        names = ", ".join(output["Failed"])
        print(f"Failed to assign: {names}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
