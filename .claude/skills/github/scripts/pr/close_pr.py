#!/usr/bin/env python3
"""Close a GitHub Pull Request.

Closes a PR with optional comment explaining the reason.
Supports idempotency: returns success if already closed.

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
    parser = argparse.ArgumentParser(description="Close a GitHub Pull Request.")
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument("--comment", default="", help="Comment to post before closing")
    parser.add_argument(
        "--comment-file", default="", help="File containing comment body",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request
    repo_flag = f"{owner}/{repo}"

    comment = args.comment
    if args.comment_file:
        if not os.path.isfile(args.comment_file):
            error_and_exit(f"Comment file not found: {args.comment_file}", 2)
        with open(args.comment_file, encoding="utf-8") as fh:
            comment = fh.read()

    state_result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", "state"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if state_result.returncode != 0:
        output = state_result.stderr or state_result.stdout
        if "not found" in output:
            error_and_exit(f"PR #{pr} not found in {repo_flag}", 2)
        error_and_exit(f"Failed to get PR state: {output}", 3)

    state = json.loads(state_result.stdout).get("state", "")

    if state in ("CLOSED", "MERGED"):
        result = {
            "success": True,
            "number": pr,
            "state": state,
            "action": "none",
            "message": f"PR already {state.lower()}",
        }
        print(json.dumps(result, indent=2))
        return 0

    if comment:
        subprocess.run(
            ["gh", "pr", "comment", str(pr), "--repo", repo_flag, "--body", comment],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    close_result = subprocess.run(
        ["gh", "pr", "close", str(pr), "--repo", repo_flag],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if close_result.returncode != 0:
        error_and_exit(
            f"Failed to close PR #{pr}: {close_result.stderr or close_result.stdout}",
            3,
        )

    result = {
        "success": True,
        "number": pr,
        "state": "CLOSED",
        "action": "closed",
        "message": "PR closed successfully",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
