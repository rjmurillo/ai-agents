#!/usr/bin/env python3
"""Get context and metadata for a GitHub Pull Request.

Retrieves comprehensive PR information including:
- Basic metadata (number, title, body, state, author)
- Branch information (head, base, commits)
- Labels and reviewers
- Optionally includes diff or changed files

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_WORKSPACE = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")),
)
sys.path.insert(0, _WORKSPACE)

from scripts.github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
)

_JSON_FIELDS = (
    "number,title,body,headRefName,baseRefName,state,author,labels,"
    "reviewRequests,commits,additions,deletions,changedFiles,"
    "mergeable,mergedAt,mergedBy,createdAt,updatedAt"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get context and metadata for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--include-diff", action="store_true",
        help="Include the PR diff (may be large)",
    )
    parser.add_argument(
        "--include-changed-files", action="store_true",
        help="Include list of changed files",
    )
    parser.add_argument(
        "--diff-stat", action="store_true",
        help="With --include-diff, return stat format instead of full diff",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]
    pr = args.pull_request
    repo_flag = f"{owner}/{repo}"

    pr_result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", _JSON_FIELDS],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if pr_result.returncode != 0:
        err_msg = pr_result.stderr or pr_result.stdout
        if "not found" in err_msg:
            error_and_exit(f"PR #{pr} not found in {repo_flag}", 2)
        error_and_exit(f"Failed to get PR #{pr}: {err_msg}", 3)

    pr_data = json.loads(pr_result.stdout)

    labels = [label.get("name", "") for label in pr_data.get("labels", [])]
    merged_by = pr_data.get("mergedBy")

    output: dict = {
        "success": True,
        "number": pr_data.get("number"),
        "title": pr_data.get("title"),
        "body": pr_data.get("body"),
        "state": pr_data.get("state"),
        "author": pr_data.get("author", {}).get("login"),
        "head_branch": pr_data.get("headRefName"),
        "base_branch": pr_data.get("baseRefName"),
        "labels": labels,
        "commits": pr_data.get("commits", {}).get("totalCount", 0),
        "additions": pr_data.get("additions"),
        "deletions": pr_data.get("deletions"),
        "changed_files": pr_data.get("changedFiles"),
        "mergeable": pr_data.get("mergeable"),
        "merged": bool(pr_data.get("mergedAt")),
        "merged_by": merged_by.get("login") if merged_by else None,
        "created_at": pr_data.get("createdAt"),
        "updated_at": pr_data.get("updatedAt"),
        "diff": None,
        "files": None,
        "owner": owner,
        "repo": repo,
    }

    if args.include_diff:
        diff_args = ["gh", "pr", "diff", str(pr), "--repo", repo_flag]
        if args.diff_stat:
            diff_args.append("--stat")
        diff_result = subprocess.run(
            diff_args, capture_output=True, text=True, timeout=60, check=False,
        )
        if diff_result.returncode == 0:
            output["diff"] = diff_result.stdout

    if args.include_changed_files:
        files_result = subprocess.run(
            ["gh", "pr", "diff", str(pr), "--repo", repo_flag, "--name-only"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if files_result.returncode == 0:
            output["files"] = [
                f for f in files_result.stdout.splitlines() if f.strip()
            ]

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
