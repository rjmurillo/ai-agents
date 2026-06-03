#!/usr/bin/env python3
"""List GitHub Pull Requests with optional filters.

Enumerates PRs in a repository with filtering capabilities:
- State (open, closed, merged, all)
- Labels (comma-separated or single label)
- Author
- Base branch
- Head branch
- Result limit

Returns the standardized skill output envelope (ADR-056) with PR metadata
under Data.PullRequests for downstream processing.

Exit codes follow ADR-035:
    0 - Success
    2 - Config / invalid params
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
    is_gh_authenticated,
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
        description="List GitHub Pull Requests with optional filters.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--state", choices=["open", "closed", "merged", "all"], default="open",
        help="PR state filter (default: open)",
    )
    parser.add_argument(
        "--label", default="",
        help="Filter by label(s). Comma-separated for multiple.",
    )
    parser.add_argument("--author", default="", help="Filter by PR author username")
    parser.add_argument("--base", default="", help="Filter by base (target) branch")
    parser.add_argument(
        "--head", default="",
        help="Filter by head (source) branch. Format: OWNER:branch or branch.",
    )
    parser.add_argument(
        "--search", default="",
        help="GitHub search query (e.g. 'fix auth is:open'). "
             "When used, --state/--label/--author/--base/--head are ignored.",
    )
    parser.add_argument(
        "--limit", type=int, default=30,
        help="Max number of PRs to return (1-1000, default: 30)",
    )
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    if not 1 <= args.limit <= 1000:
        write_skill_error(
            "Limit must be between 1 and 1000.",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="get_pull_requests.py",
        )
        return 2

    if not is_gh_authenticated():
        write_skill_error(
            "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first.",
            4,
            error_type="AuthError",
            output_format=fmt,
            script_name="get_pull_requests.py",
        )
        return 4

    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    repo_flag = f"{owner}/{repo}"

    list_args = [
        "gh", "pr", "list",
        "--repo", repo_flag,
        "--limit", str(args.limit),
        "--json", "number,title,headRefName,baseRefName,state",
    ]

    if args.search:
        # gh pr list --search ignores --state, --label, --author, --base,
        # --head flags. Only pass --search to avoid misleading behavior.
        list_args.extend(["--search", args.search])
    else:
        if args.state == "merged":
            list_args.extend(["--state", "closed"])
        elif args.state != "all":
            list_args.extend(["--state", args.state])

        if args.label:
            labels = [lbl.strip() for lbl in args.label.split(",") if lbl.strip()]
            for lbl in labels:
                list_args.extend(["--label", lbl])

        if args.author:
            list_args.extend(["--author", args.author])

        if args.base:
            list_args.extend(["--base", args.base])

        if args.head:
            list_args.extend(["--head", args.head])

    result = subprocess.run(
        list_args, capture_output=True, text=True, timeout=30, check=False,
    )

    if result.returncode != 0:
        write_skill_error(
            f"Failed to list PRs: {result.stderr or result.stdout}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name="get_pull_requests.py",
        )
        return 3

    prs = json.loads(result.stdout)

    if args.state == "merged":
        prs = [p for p in prs if p.get("state") == "MERGED"]

    pull_requests = [
        {
            "number": p.get("number"),
            "title": p.get("title"),
            "head": p.get("headRefName"),
            "base": p.get("baseRefName"),
            "state": p.get("state"),
        }
        for p in prs
    ]

    write_skill_output(
        {"PullRequests": pull_requests},
        output_format=fmt,
        human_summary=f"Found {len(pull_requests)} pull request(s)",
        status="PASS",
        script_name="get_pull_requests.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
