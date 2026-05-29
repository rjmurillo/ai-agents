#!/usr/bin/env python3
"""List GitHub Issues with optional filters.

Enumerates issues in a repository with filtering capabilities:
- State (open, closed, all)
- Labels (comma-separated or single label)
- Author
- Assignee
- Search query
- Result limit

Returns a JSON array with issue metadata for downstream processing.

Mirrors the PR-side ``get_pull_requests.py`` precedent so the
``invoke_skill_first_guard.py`` ``issue.list`` mapping resolves to a
script that can actually list issues (see issue #2110).

Exit codes follow ADR-035:
    0 - Success
    2 - Config / argument error
    3 - External error (API failure)
    4 - Auth error
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
    error_and_exit,
    resolve_repo_params,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List GitHub Issues with optional filters.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--state", choices=["open", "closed", "all"], default="open",
        help="Issue state filter (default: open)",
    )
    parser.add_argument(
        "--label", default="",
        help="Filter by label(s). Comma-separated for multiple.",
    )
    parser.add_argument(
        "--author", default="", help="Filter by issue author username",
    )
    parser.add_argument(
        "--assignee", default="",
        help="Filter by assignee username (use '@me' for self).",
    )
    parser.add_argument(
        "--search", default="",
        help="GitHub search query (e.g. 'fix auth is:open'). "
             "When used, --state/--label/--author/--assignee are ignored.",
    )
    parser.add_argument(
        "--limit", type=int, default=30,
        help="Max number of issues to return (1-1000, default: 30)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not 1 <= args.limit <= 1000:
        error_and_exit("Limit must be between 1 and 1000.", 2)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    repo_flag = f"{owner}/{repo}"

    list_args = [
        "gh", "issue", "list",
        "--repo", repo_flag,
        "--limit", str(args.limit),
        "--json", "number,title,state,labels,assignees,author,url,createdAt,updatedAt",
    ]

    if args.search:
        # gh issue list --search ignores --state, --label, --author,
        # --assignee. Only pass --search to avoid misleading behavior.
        list_args.extend(["--search", args.search])
    else:
        if args.state != "all":
            list_args.extend(["--state", args.state])

        if args.label:
            labels = [lbl.strip() for lbl in args.label.split(",") if lbl.strip()]
            for lbl in labels:
                list_args.extend(["--label", lbl])

        if args.author:
            list_args.extend(["--author", args.author])

        if args.assignee:
            list_args.extend(["--assignee", args.assignee])

    result = subprocess.run(
        list_args, capture_output=True, text=True, timeout=30, check=False,
    )

    if result.returncode != 0:
        error_and_exit(
            f"Failed to list issues: {result.stderr or result.stdout}", 3,
        )

    issues = json.loads(result.stdout)

    output = [
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "labels": [lbl.get("name") for lbl in i.get("labels", [])],
            "assignees": [a.get("login") for a in i.get("assignees", [])],
            "author": (i.get("author") or {}).get("login"),
            "url": i.get("url"),
            "createdAt": i.get("createdAt"),
            "updatedAt": i.get("updatedAt"),
        }
        for i in issues
    ]

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
