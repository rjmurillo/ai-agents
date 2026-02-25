#!/usr/bin/env python3
"""Post a reply to a GitHub PR review comment or top-level PR comment.

Posts replies using the correct endpoint for thread preservation:
- Review comments: Uses in_reply_to for thread context (Skill-PR-004)
- Issue comments: Posts to issue comments endpoint for top-level

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Config error (file not found)
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

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
        description="Post a reply to a PR review comment or top-level comment.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--comment-id", type=int, default=0,
        help="Review comment ID to reply to. Omit for top-level comment.",
    )

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Reply text (inline)")
    body_group.add_argument("--body-file", help="Path to file containing reply")
    return parser


def _resolve_body(args: argparse.Namespace) -> str:
    if args.body_file:
        resolved = Path(args.body_file).resolve()
        if ".." in Path(args.body_file).parts:
            error_and_exit(f"Path traversal detected: {args.body_file}", 1)
        if not resolved.is_file():
            error_and_exit(f"Body file not found: {args.body_file}", 2)
        return resolved.read_text(encoding="utf-8")
    return str(args.body)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    body = _resolve_body(args)
    if not body or not body.strip():
        error_and_exit("Body cannot be empty.", 1)

    pr = args.pull_request

    if args.comment_id:
        endpoint = f"repos/{owner}/{repo}/pulls/{pr}/comments/{args.comment_id}/replies"
    else:
        endpoint = f"repos/{owner}/{repo}/issues/{pr}/comments"

    result = subprocess.run(
        ["gh", "api", endpoint, "-X", "POST", "-f", f"body={body}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if result.returncode != 0:
        error_and_exit(f"Failed to post comment: {result.stderr or result.stdout}", 3)

    response = json.loads(result.stdout)

    output = {
        "success": True,
        "comment_id": response.get("id"),
        "html_url": response.get("html_url"),
        "pull_request": pr,
        "in_reply_to": args.comment_id or None,
        "created_at": response.get("created_at"),
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
