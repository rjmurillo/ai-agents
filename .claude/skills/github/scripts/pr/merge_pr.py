#!/usr/bin/env python3
"""Merge a GitHub Pull Request.

Merges a PR using the specified strategy. Supports auto-merge
for PRs with pending checks.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure)
    4 - Auth error
    6 - Not mergeable
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
    parser = argparse.ArgumentParser(description="Merge a GitHub Pull Request.")
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--strategy", choices=["merge", "squash", "rebase"], default="merge",
        help="Merge strategy (default: merge)",
    )
    parser.add_argument(
        "--delete-branch", action="store_true",
        help="Delete the head branch after merge",
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="Enable auto-merge (merge when checks pass)",
    )
    parser.add_argument("--subject", default="", help="Custom commit subject")
    parser.add_argument("--body", default="", help="Custom commit body")
    return parser


_STRATEGY_TO_REPO_FIELD = {
    "merge": "allow_merge_commit",
    "squash": "allow_squash_merge",
    "rebase": "allow_rebase_merge",
}

_BLOCKED_KEYWORDS = ("BLOCKED", "branch protection", "required status check")


def get_allowed_merge_methods(repo_flag: str) -> dict[str, bool]:
    """Query repository settings for allowed merge methods.

    Returns a dict mapping strategy names to booleans.
    """
    result = subprocess.run(
        [
            "gh", "api", f"repos/{repo_flag}",
            "--jq", "{allow_merge_commit, allow_squash_merge, allow_rebase_merge}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return {}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def validate_strategy(strategy: str, repo_settings: dict[str, bool], repo_flag: str) -> None:
    """Exit with code 1 if the requested strategy is not allowed by the repo."""
    if not repo_settings:
        return

    field = _STRATEGY_TO_REPO_FIELD.get(strategy)
    if field and not repo_settings.get(field, True):
        allowed = [
            name for name, fld in _STRATEGY_TO_REPO_FIELD.items()
            if repo_settings.get(fld, False)
        ]
        hint = f" Allowed: {', '.join(allowed)}." if allowed else ""
        error_and_exit(
            f"Strategy '{strategy}' is not allowed by {repo_flag}.{hint}",
            1,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["Owner"], resolved["Repo"]
    pr = args.pull_request
    repo_flag = f"{owner}/{repo}"

    repo_settings = get_allowed_merge_methods(repo_flag)
    validate_strategy(args.strategy, repo_settings, repo_flag)

    pr_result = subprocess.run(
        [
            "gh", "pr", "view", str(pr), "--repo", repo_flag,
            "--json", "state,mergeable,mergeStateStatus,headRefName",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if pr_result.returncode != 0:
        output = pr_result.stderr or pr_result.stdout
        if "not found" in output:
            error_and_exit(f"PR #{pr} not found in {repo_flag}", 2)
        error_and_exit(f"Failed to get PR state: {output}", 3)

    pr_data = json.loads(pr_result.stdout)

    if pr_data.get("state") == "MERGED":
        result = {
            "success": True,
            "number": pr,
            "state": "MERGED",
            "action": "none",
            "message": "PR already merged",
        }
        print(json.dumps(result, indent=2))
        return 0

    if pr_data.get("state") == "CLOSED":
        error_and_exit(f"PR #{pr} is closed and cannot be merged", 6)

    merge_args = [
        "gh", "pr", "merge", str(pr),
        "--repo", repo_flag,
        f"--{args.strategy}",
    ]

    if args.delete_branch:
        merge_args.append("--delete-branch")

    if args.auto:
        merge_args.append("--auto")

    if args.subject:
        merge_args.extend(["--subject", args.subject])

    if args.body:
        merge_args.extend(["--body", args.body])

    merge_result = subprocess.run(
        merge_args, capture_output=True, text=True, timeout=60, check=False,
    )

    if merge_result.returncode != 0:
        output = merge_result.stderr or merge_result.stdout
        if any(kw in output for kw in ("not mergeable", "cannot be merged", "conflicts")):
            error_and_exit(f"PR #{pr} is not mergeable: {output}", 6)
        if not args.auto and any(kw in output for kw in _BLOCKED_KEYWORDS):
            error_and_exit(
                f"PR #{pr} is blocked by branch protection policy: {output}\n"
                "Hint: use --auto to enable auto-merge when checks pass.",
                6,
            )
        error_and_exit(f"Failed to merge PR #{pr}: {output}", 3)

    action = "auto-merge-enabled" if args.auto else "merged"
    state = "PENDING" if args.auto else "MERGED"
    message = "Auto-merge enabled" if args.auto else "PR merged successfully"

    result = {
        "success": True,
        "number": pr,
        "state": state,
        "action": action,
        "strategy": args.strategy,
        "branch_deleted": args.delete_branch,
        "message": message,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
