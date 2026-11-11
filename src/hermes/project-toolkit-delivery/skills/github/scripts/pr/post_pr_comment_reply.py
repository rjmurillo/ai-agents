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
from typing import Any

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
_script_dir = os.path.dirname(__file__)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from github_core.api import (
    assert_gh_authenticated,
    error_and_exit,
    resolve_repo_params,
    sanitize_failure_detail,
)
from github_core.validation import resolved_body_error
from pr_comment_dedupe import (
    LOOKUP_TIMEOUT_SECONDS,
    body_matches,
    first_by_author,
    flatten_pages,
    paginated_args,
    thread_comments,
)

_HELP_EPILOG = """\
examples:
  %(prog)s --pull-request 123 --body "Thanks, fixed in abc1234"
  %(prog)s --pull-request 123 --comment-id 456789 --body-file reply.md
  %(prog)s --pull-request 123 --body "Thanks, fixed in abc1234" --dry-run

A retry is safe: when the same author already posted an identical body in the
thread (or in the PR conversation when --comment-id is omitted), nothing is
posted. The result reports action SKIP, reason duplicate, and the existing
comment_id.

exit codes:
  0  success (posted, previewed with --dry-run, or skipped as a duplicate)
  2  config/usage error, or the pull request or comment was not found
  3  external error (API failure, including a failed duplicate check: nothing is posted)
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Post a reply to a PR review comment or top-level comment.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the reply and report the target endpoint; post nothing",
    )
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


def _check_target_exists(owner: str, repo: str, pr: int, comment_id: int) -> None:
    """Read the reply target, so a dry run fails like a real run on a missing PR or comment.

    A threaded reply posts to the PR-scoped endpoint, so the comment must belong to ``pr``.
    """
    if comment_id:
        endpoint = f"repos/{owner}/{repo}/pulls/comments/{comment_id}"
    else:
        endpoint = f"repos/{owner}/{repo}/pulls/{pr}"
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        error_and_exit("Timed out after 30s reading the reply target; nothing was posted.", 3)
    if result.returncode != 0:
        if _is_not_found(result):
            error_and_exit(_not_found_message(owner, repo, pr, comment_id), 2)
        error_and_exit(f"Failed to read the reply target: {result.stderr or result.stdout}", 3)
    if comment_id and not _comment_belongs_to_pr(result.stdout, pr):
        error_and_exit(_not_found_message(owner, repo, pr, comment_id), 2)


def _comment_belongs_to_pr(comment_json: str, pr: int) -> bool:
    """True when the review comment's ``pull_request_url`` ends with ``/pulls/<pr>``."""
    try:
        url = json.loads(comment_json).get("pull_request_url", "")
    except (ValueError, AttributeError):
        return False
    return isinstance(url, str) and url.rstrip("/").endswith(f"/pulls/{pr}")


def _lookup_failure(what: str, detail: str) -> str:
    return (
        f"Failed to {what} to check for a duplicate: {detail}. Nothing was posted. "
        "Retry the same command: the post waits for a complete read so a retry never duplicates."
    )


def _read_all_comments(endpoint: str, what: str, not_found: str) -> list[dict[str, Any]]:
    """Read every page of ``endpoint`` or exit; a partial read never counts as "no duplicate"."""
    try:
        result = subprocess.run(
            ["gh", "api", *paginated_args(endpoint)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=LOOKUP_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        error_and_exit(_lookup_failure(what, f"timed out after {LOOKUP_TIMEOUT_SECONDS}s"), 3)
    if result.returncode != 0:
        if _is_not_found(result):
            error_and_exit(not_found, 2)
        detail = sanitize_failure_detail(result.stderr or result.stdout, limit=400)
        error_and_exit(_lookup_failure(what, detail or "no output from gh"), 3)
    try:
        comments = flatten_pages(result.stdout)
    except ValueError as exc:
        error_and_exit(_lookup_failure(what, f"unreadable response ({exc})"), 3)
    return comments


def _authenticated_login() -> str:
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        error_and_exit(_lookup_failure("read the authenticated user", "timed out after 30s"), 3)
    login = (result.stdout or "").strip()
    if result.returncode != 0 or not login:
        detail = sanitize_failure_detail(result.stderr or result.stdout, limit=400)
        error_and_exit(_lookup_failure("read the authenticated user", detail or "empty login"), 3)
    return login


def _find_duplicate(
    owner: str, repo: str, pr: int, comment_id: int, body: str
) -> dict[str, Any] | None:
    """Return an earlier comment by the same author with an identical body, or None.

    With ``comment_id`` the search covers that review thread. Without it, the PR
    conversation. The authenticated user is looked up only when some comment has
    the same body, so the common first post costs one read.
    """
    not_found = _not_found_message(owner, repo, pr, comment_id)
    if comment_id:
        endpoint = f"repos/{owner}/{repo}/pulls/{pr}/comments"
        reviews = _read_all_comments(
            endpoint, f"read the review comments of {owner}/{repo}#{pr}", not_found
        )
        thread = thread_comments(reviews, comment_id)
        if thread is None:
            error_and_exit(not_found, 2)
        candidates = thread or []
    else:
        endpoint = f"repos/{owner}/{repo}/issues/{pr}/comments"
        candidates = _read_all_comments(
            endpoint, f"read the comments of {owner}/{repo}#{pr}", not_found
        )
    same_body = body_matches(candidates, body)
    if not same_body:
        return None
    return first_by_author(same_body, _authenticated_login())


def _skip_payload(
    existing: dict[str, Any], pr: int, comment_id: int, dry_run: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": True,
        "action": "would_skip" if dry_run else "SKIP",
        "reason": "duplicate",
        "comment_id": existing.get("id"),
        "html_url": existing.get("html_url"),
        "pull_request": pr,
        "in_reply_to": comment_id or None,
    }
    if dry_run:
        payload["dryRun"] = True
    return payload


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
    body_error = resolved_body_error(body, from_file=bool(args.body_file))
    if body_error:
        error_and_exit(body_error, 2)

    pr = args.pull_request

    if args.comment_id:
        endpoint = f"repos/{owner}/{repo}/pulls/{pr}/comments/{args.comment_id}/replies"
    else:
        endpoint = f"repos/{owner}/{repo}/issues/{pr}/comments"

    if args.dry_run:
        _check_target_exists(owner, repo, pr, args.comment_id)
        existing = _find_duplicate(owner, repo, pr, args.comment_id, body)
        if existing is not None:
            print(json.dumps(_skip_payload(existing, pr, args.comment_id, True), indent=2))
            return 0
        print(
            json.dumps(
                {
                    "success": True,
                    "action": "would_post",
                    "dryRun": True,
                    "pull_request": pr,
                    "in_reply_to": args.comment_id or None,
                    "endpoint": endpoint,
                    "body_chars": len(body),
                },
                indent=2,
            )
        )
        return 0

    existing = _find_duplicate(owner, repo, pr, args.comment_id, body)
    if existing is not None:
        print(json.dumps(_skip_payload(existing, pr, args.comment_id, False), indent=2))
        return 0

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
