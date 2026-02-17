#!/usr/bin/env python3
"""Get context and metadata for a GitHub Issue.

Retrieves issue information including title, body, labels, milestone, state.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root:
    _lib_dir = os.path.join(_plugin_root, "lib")
elif _workspace:
    _lib_dir = os.path.join(_workspace, ".claude", "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get context and metadata for a GitHub Issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]

    fields = "number,title,body,state,author,labels,milestone,assignees,createdAt,updatedAt"
    result = subprocess.run(
        [
            "gh", "issue", "view", str(args.issue),
            "--repo", f"{owner}/{repo}",
            "--json", fields,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        error_and_exit(
            f"Issue #{args.issue} not found or API error (exit code {result.returncode})",
            2,
        )

    try:
        issue_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        error_and_exit("Failed to parse issue JSON", 3)

    if not issue_data:
        error_and_exit("Failed to parse issue JSON", 3)

    labels = [label["name"] for label in issue_data.get("labels", [])]
    assignees = [a["login"] for a in issue_data.get("assignees", [])]
    milestone_obj = issue_data.get("milestone")
    milestone = milestone_obj["title"] if milestone_obj else None

    output = {
        "success": True,
        "number": issue_data["number"],
        "title": issue_data["title"],
        "body": issue_data.get("body", ""),
        "state": issue_data["state"],
        "author": issue_data.get("author", {}).get("login", ""),
        "labels": labels,
        "milestone": milestone,
        "assignees": assignees,
        "created_at": issue_data.get("createdAt", ""),
        "updated_at": issue_data.get("updatedAt", ""),
        "owner": owner,
        "repo": repo,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
