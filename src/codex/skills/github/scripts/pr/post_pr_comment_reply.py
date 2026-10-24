#!/usr/bin/env python3
"""Post a reply to a GitHub PR review comment or top-level PR comment.

Posts replies using the correct endpoint for thread preservation:
- Review comments: Uses in_reply_to for thread context (Skill-PR-004)
- Issue comments: Posts to issue comments endpoint for top-level

Exit codes follow ADR-035:
    0 - Success
    2 - Config/usage error (invalid parameters, file not found, comment or PR not found)
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
_workspace = os.environ.get("GITHUB_WORKSPACE")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
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

from github_core.api import (
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
)
from github_core.validation import inline_body_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Post a reply to a PR review comment or top-level comment.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--comment-id",
        type=int,
        default=0,
        help="Review comment ID to reply to. Omit for top-level comment.",
    )

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Reply text (inline)")
    body_group.add_argument("--body-file", help="Path to file containing reply")
    return parser


_NOT_FOUND_PATTERN = re.compile(r'HTTP 404|"status"\s*:\s*"404"')


def _is_not_found(result: subprocess.CompletedProcess[str]) -> bool:
    """Return True when gh reported HTTP 404 on stderr or in the JSON body."""
    combined = f"{result.stderr or ''}\n{result.stdout or ''}"
    return _NOT_FOUND_PATTERN.search(combined) is not None


def _not_found_message(owner: str, repo: str, pr: int, comment_id: int) -> str:
    if comment_id:
        return f"Comment {comment_id} not found on {owner}/{repo}#{pr}"
    return f"Pull request {owner}/{repo}#{pr} not found"


def _resolve_body(args: argparse.Namespace) -> str:
    if args.body_file:
        from github_core.validation import assert_valid_body_file, read_body_file_text

        assert_valid_body_file(args.body_file)
        try:
            # The strict shared reader (issue #6919), keeping the git-dir reply flow.
            return read_body_file_text(args.body_file, allow_git_dir=True)
        except (OSError, ValueError) as exc:
            error_and_exit(f"Failed to read body file {args.body_file}: {exc}", 2)
    return str(args.body)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    body = _resolve_body(args)
    body_error = inline_body_error(body)
    if body_error:
        error_and_exit(body_error, 2)

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
        if _is_not_found(result):
            error_and_exit(_not_found_message(owner, repo, pr, args.comment_id), 2)
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
