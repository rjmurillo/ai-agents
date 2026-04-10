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
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get context and metadata for a GitHub Issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    fmt = get_output_format(args.output_format)

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
        write_skill_error(
            f"Issue #{args.issue} not found or API error (exit code {result.returncode})",
            2,
            error_type="NotFound",
            output_format=fmt,
            script_name="get_issue_context.py",
        )
        raise SystemExit(2)

    try:
        issue_data = json.loads(result.stdout)
    except json.JSONDecodeError as err:
        write_skill_error(
            "Failed to parse issue JSON",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="get_issue_context.py",
        )
        raise SystemExit(3) from err

    if not issue_data:
        write_skill_error(
            "Failed to parse issue JSON",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="get_issue_context.py",
        )
        raise SystemExit(3)

    labels = [label["name"] for label in issue_data.get("labels", [])]
    assignees = [a["login"] for a in issue_data.get("assignees", [])]
    milestone_obj = issue_data.get("milestone")
    milestone = milestone_obj["title"] if milestone_obj else None

    data = {
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

    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"Issue #{args.issue}: {issue_data['title']} ({issue_data['state']})",
        status="PASS",
        script_name="get_issue_context.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
