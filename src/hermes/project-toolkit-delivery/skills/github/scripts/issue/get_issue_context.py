#!/usr/bin/env python3
"""Get context and metadata for a GitHub Issue.

Retrieves issue information including title, body, labels, milestone, state.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error
    2 - Config or usage error
    3 - External error (API failure, or the issue was not found;
        Error.Type is NotFound for a missing issue, ApiError otherwise)
    4 - Auth error (not authenticated)
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

from github_core import (
    add_output_format_arg,
    assert_gh_authenticated,
    get_output_format,
    resolve_repo_params,
    write_skill_error,
    write_skill_output,
)
from github_core import (
    env_timeout_seconds as _env_timeout_seconds,
)

GH_TIMEOUT_SECONDS = _env_timeout_seconds()

# gh words a missing issue two ways: REST reports "Not Found (HTTP 404)", and
# GraphQL reports "Could not resolve to an issue or pull request with the
# number of N". "Could not resolve host" is a transport fault and must not match.
_ISSUE_NOT_FOUND_MARKERS = (
    "not found",
    "could not resolve to an issue",
)


def _is_issue_not_found(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _ISSUE_NOT_FOUND_MARKERS)


_HELP_EPILOG = """\
examples:
  %(prog)s --issue 123
  %(prog)s --issue 123 --output-format json

exit codes:
  0  success
  2  config or usage error
  3  external error (API failure, or the issue was not found; see Error.Type)
  4  auth error (not authenticated)
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get context and metadata for a GitHub Issue.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "view",
                str(args.issue),
                "--repo",
                f"{owner}/{repo}",
                "--json",
                fields,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        write_skill_error(
            f"gh issue view timed out after {GH_TIMEOUT_SECONDS}s",
            3,
            error_type="Timeout",
            output_format=fmt,
            script_name="get_issue_context.py",
        )
        raise SystemExit(3) from err

    if result.returncode != 0:
        # A reported miss and any other gh failure (network, server, rate
        # limit) both exit 3 per ADR-035. Error.Type separates them:
        # NotFound versus ApiError.
        detail = (result.stderr or result.stdout or "").strip()
        if _is_issue_not_found(detail):
            write_skill_error(
                f"Issue #{args.issue} not found in {owner}/{repo}",
                3,
                error_type="NotFound",
                output_format=fmt,
                script_name="get_issue_context.py",
            )
            raise SystemExit(3)
        write_skill_error(
            f"Failed to get issue #{args.issue} (gh exit {result.returncode}): {detail}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="get_issue_context.py",
        )
        raise SystemExit(3)

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
