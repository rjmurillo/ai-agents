#!/usr/bin/env python3
"""Create a new GitHub Issue.

Creates issues with title, body, and labels.
Supports both inline body text and file-based body content.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = File not found
    3 = API error
    4 = Not authenticated
"""

import argparse
import json
import os
import re
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


def new_issue(
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    labels: str = "",
) -> dict:
    """Create a new GitHub issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        title: Issue title.
        body: Issue body text.
        labels: Comma-separated label names.

    Returns:
        Dict with issue number and URL.
    """
    gh_args = ["gh", "issue", "create", "--repo", f"{owner}/{repo}", "--title", title]

    if body.strip():
        gh_args.extend(["--body", body])

    if labels.strip():
        gh_args.extend(["--label", labels])

    result = subprocess.run(gh_args, capture_output=True, text=True)

    if result.returncode != 0:
        stderr = result.stderr or result.stdout
        write_error_and_exit(f"Failed to create issue: {stderr}", 3)

    output_text = result.stdout.strip()
    match = re.search(r"issues/(\d+)", output_text)
    if not match:
        write_error_and_exit(
            f"Could not parse issue number from result: {output_text}", 3
        )

    issue_number = int(match.group(1))

    return {
        "Success": True,
        "IssueNumber": issue_number,
        "IssueUrl": output_text,
        "Title": title,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new GitHub issue")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--title", required=True, help="Issue title")
    parser.add_argument("--body", default="", help="Issue body text")
    parser.add_argument("--body-file", help="Path to file containing issue body")
    parser.add_argument("--labels", default="", help="Comma-separated labels")
    args = parser.parse_args()

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)

    if not args.title.strip():
        write_error_and_exit("Title cannot be empty.", 1)

    body = args.body
    if args.body_file:
        if not os.path.isfile(args.body_file):
            write_error_and_exit(f"Body file not found: {args.body_file}", 2)
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()

    output = new_issue(
        resolved["owner"], resolved["repo"],
        args.title, body, args.labels,
    )

    print(json.dumps(output, indent=2))
    print(f"Created issue #{output['IssueNumber']}", file=sys.stderr)
    print(f"  Title: {output['Title']}", file=sys.stderr)
    print(f"  URL: {output['IssueUrl']}", file=sys.stderr)


if __name__ == "__main__":
    main()
