#!/usr/bin/env python3
"""Get context and metadata for a GitHub Issue.

Retrieves issue information including title, body, labels,
milestone, state, assignees, and timestamps.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = Not found
    3 = API error
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


def get_issue_context(owner: str, repo: str, issue_number: int) -> dict:
    """Fetch issue context from GitHub.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue_number: The issue number.

    Returns:
        Dict with issue metadata.
    """
    fields = (
        "number,title,body,state,author,labels,"
        "milestone,assignees,createdAt,updatedAt"
    )
    result = subprocess.run(
        [
            "gh", "issue", "view", str(issue_number),
            "--repo", f"{owner}/{repo}",
            "--json", fields,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        if "not found" in result.stderr.lower():
            write_error_and_exit(
                f"Issue #{issue_number} not found in {owner}/{repo}", 2
            )
        write_error_and_exit(
            f"Issue #{issue_number} not found or API error "
            f"(exit code {result.returncode})", 2
        )

    issue = json.loads(result.stdout)

    if not issue:
        write_error_and_exit("Failed to parse issue JSON", 3)

    milestone = issue.get("milestone")
    milestone_title = milestone.get("title") if milestone else None

    return {
        "Success": True,
        "Number": issue["number"],
        "Title": issue["title"],
        "Body": issue.get("body", ""),
        "State": issue["state"],
        "Author": issue.get("author", {}).get("login", ""),
        "Labels": [label["name"] for label in issue.get("labels", [])],
        "Milestone": milestone_title,
        "Assignees": [a["login"] for a in issue.get("assignees", [])],
        "CreatedAt": issue.get("createdAt", ""),
        "UpdatedAt": issue.get("updatedAt", ""),
        "Owner": owner,
        "Repo": repo,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Get issue context and metadata")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument(
        "--issue", type=int, required=True, help="Issue number"
    )
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    output = get_issue_context(
        resolved["owner"], resolved["repo"], args.issue
    )

    print(json.dumps(output, indent=2))
    print(
        f"Issue #{output['Number']}: {output['Title']}",
        file=sys.stderr,
    )
    state = output["State"]
    author = output["Author"]
    print(
        f"  State: {state} | Author: @{author}",
        file=sys.stderr,
    )
    if output["Labels"]:
        labels = ", ".join(output["Labels"])
        print(f"  Labels: {labels}", file=sys.stderr)


if __name__ == "__main__":
    main()
