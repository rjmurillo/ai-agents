#!/usr/bin/env python3
"""Assign users to a GitHub Issue.

Supports @me shorthand for the current authenticated user.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
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

_HELP_EPILOG = """\
examples:
  %(prog)s --issue 123 --assignees octocat
  %(prog)s --issue 123 --assignees octocat hubot --output-format json

exit codes:
  0  success
  2  invalid owner or repo, or plugin lib missing
  3  external error (API failure)
  4  auth error (not authenticated)
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assign users to a GitHub Issue.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument(
        "--assignees",
        nargs="+",
        required=True,
        help='GitHub usernames to assign. Use "@me" for current user.',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the assignees that would be added; change nothing",
    )
    add_output_format_arg(parser)
    return parser


def _check_issue_exists(owner: str, repo: str, issue: int, fmt: str) -> None:
    """Read the issue, so a dry run fails like a real assignment on a missing issue."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue), "--repo", f"{owner}/{repo}", "--json", "number"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        write_skill_error(
            f"Timed out after 30s reading issue #{issue} in {owner}/{repo}; nothing was assigned.",
            3,
            error_type="Timeout",
            output_format=fmt,
            script_name="set_issue_assignee.py",
            extra={"issue": issue},
        )
        raise SystemExit(3) from None
    if result.returncode == 0:
        return
    write_skill_error(
        f"Failed to read issue #{issue} in {owner}/{repo}: "
        f"{result.stderr.strip() or result.stdout.strip()}",
        3,
        error_type="ApiError",
        output_format=fmt,
        script_name="set_issue_assignee.py",
        extra={"issue": issue},
    )
    raise SystemExit(3)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    fmt = get_output_format(args.output_format)

    assignees: list[str] = args.assignees
    if not assignees:
        print("No assignees to add.", file=sys.stderr)
        return 0

    if args.dry_run:
        _check_issue_exists(owner, repo, args.issue, fmt)
        write_skill_output(
            {
                "issue": args.issue,
                "action": "would_assign",
                "wouldAssign": list(assignees),
                "dryRun": True,
            },
            output_format=fmt,
            human_summary=f"Dry run: would assign {len(assignees)} user(s) to issue #{args.issue}",
            status="PASS",
            script_name="set_issue_assignee.py",
        )
        return 0

    applied: list[str] = []
    failed: list[str] = []

    for assignee in assignees:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "edit",
                str(args.issue),
                "--repo",
                f"{owner}/{repo}",
                "--add-assignee",
                assignee,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            applied.append(assignee)
        else:
            failed.append(assignee)

    data = {
        "issue": args.issue,
        "applied": applied,
        "failed": failed,
        "total_applied": len(applied),
    }

    if failed:
        write_skill_error(
            f"Failed to assign: {', '.join(failed)}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="set_issue_assignee.py",
            extra=data,
        )
        raise SystemExit(3)

    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"Assigned {len(applied)} user(s) to issue #{args.issue}",
        status="PASS",
        script_name="set_issue_assignee.py",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
