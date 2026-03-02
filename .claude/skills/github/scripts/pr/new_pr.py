#!/usr/bin/env python3
"""Create a new GitHub Pull Request.

Validates the title matches conventional commit format before creation.
Supports draft PRs and body from file.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters (bad title format, missing body file)
    3 = API error (creation failed)
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
from github_core.validation import test_safe_file_path

CONVENTIONAL_COMMIT_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)(\(.+\))?!?: .+"
)


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        write_error_and_exit("Could not determine current branch", 1)
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new GitHub Pull Request")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--title", required=True, help="PR title (conventional commit format)")
    body_group = parser.add_mutually_exclusive_group()
    body_group.add_argument("--body", help="PR body text")
    body_group.add_argument("--body-file", help="Path to file containing PR body")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    parser.add_argument("--head", help="Head branch (default: current branch)")
    parser.add_argument("--draft", action="store_true", help="Create as draft PR")
    args = parser.parse_args()

    if not CONVENTIONAL_COMMIT_RE.match(args.title):
        write_error_and_exit(
            f"Title must match conventional commit format "
            f"(e.g., 'feat: add feature', 'fix(scope): description'). "
            f"Got: '{args.title}'",
            1,
        )

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    head = args.head or get_current_branch()

    body = args.body
    if args.body_file:
        if not test_safe_file_path(args.body_file):
            write_error_and_exit(f"Path traversal attempt detected: {args.body_file}", 1)
        if not os.path.exists(args.body_file):
            write_error_and_exit(f"Body file not found: {args.body_file}", 1)
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()

    cmd = [
        "gh", "pr", "create",
        "--repo", f"{owner}/{repo}",
        "--title", args.title,
        "--base", args.base,
        "--head", head,
    ]

    if body:
        cmd.extend(["--body", body])
    else:
        cmd.extend(["--body", ""])

    if args.draft:
        cmd.append("--draft")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        write_error_and_exit(f"Failed to create PR: {result.stderr}", 3)

    pr_url = result.stdout.strip()

    # Extract PR number from URL (format: https://github.com/owner/repo/pull/123)
    pr_number = None
    url_match = re.search(r"/pull/(\d+)", pr_url)
    if url_match:
        pr_number = int(url_match.group(1))

    output = {
        "Success": True,
        "Number": pr_number,
        "Url": pr_url,
        "Title": args.title,
        "Base": args.base,
        "Head": head,
        "IsDraft": args.draft,
    }
    print(json.dumps(output, indent=2))
    print(f"Created PR #{pr_number} in {owner}/{repo}", file=sys.stderr)
    print(f"  URL: {pr_url}", file=sys.stderr)


if __name__ == "__main__":
    main()
