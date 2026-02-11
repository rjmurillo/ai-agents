#!/usr/bin/env python3
"""List GitHub Pull Requests with optional filters.

Enumerates PRs in a repository with filtering capabilities:
- State (open, closed, merged, all)
- Labels (comma-separated or single label)
- Author
- Base branch
- Head branch
- Result limit

Returns a JSON array with PR metadata for downstream processing.

Exit codes follow ADR-035:
    0 - Success
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
        "--limit", type=int, default=30,
        help="Max number of PRs to return (1-1000, default: 30)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not 1 <= args.limit <= 1000:
        error_and_exit("Limit must be between 1 and 1000.", 1)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]
    repo_flag = f"{owner}/{repo}"

    list_args = [
        "gh", "pr", "list",
        "--repo", repo_flag,
        "--limit", str(args.limit),
        "--json", "number,title,headRefName,baseRefName,state",
    ]

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
        error_and_exit(
            f"Failed to list PRs: {result.stderr or result.stdout}", 3,
        )

    prs = json.loads(result.stdout)

    if args.state == "merged":
        prs = [p for p in prs if p.get("state") == "MERGED"]

    output = [
        {
            "number": p.get("number"),
            "title": p.get("title"),
            "head": p.get("headRefName"),
            "base": p.get("baseRefName"),
            "state": p.get("state"),
        }
        for p in prs
    ]

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
