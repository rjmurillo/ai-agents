#!/usr/bin/env python3
"""Create a new inline review comment on a line of a pull request diff.

The other PR comment scripts only reply to an existing thread or post a
top-level comment. This one starts a thread on a diff line:

1. Resolve the pull request head commit (the API needs ``commit_id``).
2. POST to ``repos/{owner}/{repo}/pulls/{pr}/comments`` with the path, line,
   and side.

Output: a created comment and every API failure print the standard skill
envelope (Success, Data, Error, Metadata) to stdout. Argument and body
validation run before any API call and report on stderr.

Exit codes follow ADR-035:
    0 - Success
    2 - Config/usage error (invalid body, PR not found, line not in the diff,
        bad request, session refuses GitHub)
    3 - External error (API failure, rate limit, timeout)
    4 - Auth error (not authenticated, permission denied)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
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
    GhAuthStatus,
    assert_gh_authenticated,
    classify_gh_failure_text,
    error_and_exit,
    resolve_repo_params,
    sanitize_failure_detail,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)
from github_core.validation import assert_valid_body_file, inline_body_error

_SIDES = ("LEFT", "RIGHT")
_HEAD_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_HTTP_STATUS_PATTERN = re.compile(r"\bHTTP\s+(\d{3})\b|\"status\"\s*:\s*\"(\d{3})\"")
_API_TIMEOUT_SECONDS = 30
_SCRIPT_NAME = "new_pr_review_comment.py"
_RATE_LIMITED = frozenset({GhAuthStatus.RATE_LIMITED, GhAuthStatus.SECONDARY_RATE_LIMITED})


class CommentApiError(Exception):
    """An API step failed. main() reports it as a skill error envelope."""

    def __init__(self, message: str, exit_code: int, error_type: str) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.error_type = error_type


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError(f"{value!r} must be 1 or greater")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new inline review comment on a PR diff line.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=_positive_int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--path",
        required=True,
        help="File path relative to the repository root",
    )
    parser.add_argument(
        "--line",
        type=_positive_int,
        required=True,
        help="File line number on the chosen side. It must fall inside the PR diff",
    )
    parser.add_argument(
        "--side",
        choices=_SIDES,
        default="RIGHT",
        help="Diff side: RIGHT for added or unchanged lines, LEFT for removed lines",
    )

    body_group = parser.add_mutually_exclusive_group(required=True)
    body_group.add_argument("--body", help="Comment text (inline)")
    body_group.add_argument("--body-file", help="Path to file containing the comment")
    add_output_format_arg(parser)
    return parser


def _http_status(text: str) -> int | None:
    match = _HTTP_STATUS_PATTERN.search(text)
    if match is None:
        return None
    return int(match.group(1) or match.group(2))


def _classify_failure(status: int | None, text: str) -> tuple[int, str]:
    """Map an HTTP status to an ADR-035 exit code and an envelope error type.

    400 and 422 mean the request named a path or line the API rejects
    (usage). 401 and 403 mean auth, unless the text shows a quota refusal
    (external, retryable) or a session that refuses GitHub (config, matching
    the github_core auth preflight).
    """
    if status in (400, 422):
        return 2, "InvalidParams"
    if status in (401, 403):
        kind = classify_gh_failure_text(text)
        if kind in _RATE_LIMITED:
            return 3, "RateLimitError"
        if kind is GhAuthStatus.TRANSPORT_BLOCKED:
            return 2, "General"
        if kind is GhAuthStatus.INVALID_CREDENTIALS:
            return 4, "AuthError"
    return 3, "ApiError"


def _fail(action: str, result: subprocess.CompletedProcess[str], notfound: str) -> NoReturn:
    text = f"{result.stderr or ''}\n{result.stdout or ''}"
    status = _http_status(text)
    if status == 404:
        raise CommentApiError(notfound, 2, "NotFound")
    detail = sanitize_failure_detail(text, limit=400) or "no output from gh"
    exit_code, error_type = _classify_failure(status, text)
    raise CommentApiError(f"Failed to {action}: {detail}", exit_code, error_type)


def _run_gh_api(args: list[str], action: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", "api", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_API_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise CommentApiError(
            f"Timed out after {_API_TIMEOUT_SECONDS}s trying to {action}", 3, "Timeout"
        ) from None


def _resolve_body(args: argparse.Namespace) -> str:
    if args.body_file:
        assert_valid_body_file(args.body_file)
        return Path(args.body_file).read_text(encoding="utf-8")
    return str(args.body)


def _get_head_sha(owner: str, repo: str, pr: int) -> str:
    action = f"read the head commit of {owner}/{repo}#{pr}"
    result = _run_gh_api([f"repos/{owner}/{repo}/pulls/{pr}", "--jq", ".head.sha"], action)
    if result.returncode != 0:
        _fail(action, result, f"Pull request {owner}/{repo}#{pr} not found")
    sha = (result.stdout or "").strip()
    if not _HEAD_SHA_PATTERN.match(sha):
        raise CommentApiError(
            f"Unexpected head commit for {owner}/{repo}#{pr}: {sha[:80]!r}", 3, "ApiError"
        )
    return sha


def _post_comment(
    owner: str, repo: str, args: argparse.Namespace, body: str, head_sha: str
) -> dict[str, Any]:
    pr = args.pull_request
    action = f"post a review comment on {owner}/{repo}#{pr} at {args.path}:{args.line}"
    endpoint = f"repos/{owner}/{repo}/pulls/{pr}/comments"
    result = _run_gh_api(
        [
            endpoint,
            "-X",
            "POST",
            "-f",
            f"body={body}",
            "-f",
            f"commit_id={head_sha}",
            "-f",
            f"path={args.path}",
            "-F",
            f"line={args.line}",
            "-f",
            f"side={args.side}",
        ],
        action,
    )
    if result.returncode != 0:
        _fail(action, result, f"Pull request {owner}/{repo}#{pr} not found")
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise CommentApiError(
            f"GitHub returned a non-JSON response to {action}", 3, "ApiError"
        ) from None
    if not isinstance(parsed, dict):
        raise CommentApiError(f"GitHub returned a non-object response to {action}", 3, "ApiError")
    response: dict[str, Any] = parsed
    return response


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated(rest_only=True)
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    body = _resolve_body(args)
    body_error = inline_body_error(body)
    if body_error:
        error_and_exit(body_error, 2)

    try:
        head_sha = _get_head_sha(owner, repo, args.pull_request)
        response = _post_comment(owner, repo, args, body, head_sha)
    except CommentApiError as failure:
        write_skill_error(
            failure.message,
            failure.exit_code,
            error_type=failure.error_type,
            output_format=fmt,
            script_name=_SCRIPT_NAME,
            extra={
                "pull_request": args.pull_request,
                "path": args.path,
                "line": args.line,
                "side": args.side,
            },
        )
        return failure.exit_code

    output = {
        "comment_id": response.get("id"),
        "html_url": response.get("html_url"),
        "pull_request": args.pull_request,
        "path": args.path,
        "line": args.line,
        "side": args.side,
        "commit_id": head_sha,
        "created_at": response.get("created_at"),
    }
    write_skill_output(
        output,
        output_format=fmt,
        human_summary=f"Created review comment on #{args.pull_request} at {args.path}:{args.line}",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
