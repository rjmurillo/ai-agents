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
        description="Assign users to a GitHub Issue.",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]

    assignees: list[str] = args.assignees
    if not assignees:
        print("No assignees to add.", file=sys.stderr)
        return 0

    applied: list[str] = []
    failed: list[str] = []

    for assignee in assignees:
        result = subprocess.run(
            [
                "gh", "issue", "edit", str(args.issue),
                "--repo", f"{owner}/{repo}",
                "--add-assignee", assignee,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            applied.append(assignee)
        else:
            failed.append(assignee)

    output = {
        "success": len(failed) == 0,
        "issue": args.issue,
        "applied": applied,
        "failed": failed,
        "total_applied": len(applied),
    }

    print(json.dumps(output, indent=2))

    if failed:
        error_and_exit(f"Failed to assign: {', '.join(failed)}", 3)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
