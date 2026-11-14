#!/usr/bin/env python3
"""Close a GitHub Pull Request.

Closes a PR with optional comment explaining the reason.
Supports idempotency: returns success if already closed.
A failed closing comment stops the run with exit 3 before the close call.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure, or the closing comment failed so the PR stays open)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
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
from github_core.not_found import is_pr_not_found
from github_core.validation import assert_valid_body_file, read_body_file_text
from pr_comment_dedupe import (
    LOOKUP_TIMEOUT_SECONDS,
    body_matches,
    first_by_author,
    flatten_pages,
    paginated_args,
)

_HELP_EPILOG = """\
examples:
  %(prog)s --pull-request 123
  %(prog)s --pull-request 123 --comment "Superseded by #130"

exit codes:
  0  success
  2  not found
  3  external error (API failure, including a failed closing comment: the PR stays open)
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Close a GitHub Pull Request.",
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
    parser.add_argument("--comment", default="", help="Comment to post before closing")
    parser.add_argument(
        "--comment-file",
        default="",
        help="File containing comment body",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read the PR state and report what would happen; comment and close nothing",
    )
    return parser


def _lookup_failure(what: str, detail: str) -> str:
    return (
        f"Failed to {what} to check for a duplicate closing comment: {detail}. "
        "The PR was NOT closed and nothing was posted. "
        "Retry the same command once the API error clears."
    )


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


def _find_existing_closing_comment(
    owner: str, repo: str, pr: int, comment: str
) -> dict[str, Any] | None:
    """Return an existing conversation comment by the same author with an identical body."""
    endpoint = f"repos/{owner}/{repo}/issues/{pr}/comments"
    what = f"read the comments of {owner}/{repo}#{pr}"
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
        detail = sanitize_failure_detail(result.stderr or result.stdout, limit=400)
        error_and_exit(_lookup_failure(what, detail or "no output from gh"), 3)
    try:
        comments = flatten_pages(result.stdout)
    except ValueError as exc:
        error_and_exit(_lookup_failure(what, f"unreadable response ({exc})"), 3)
    same_body = body_matches(comments, comment)
    if not same_body:
        return None
    return first_by_author(same_body, _authenticated_login())


def _report_noop_or_plan(
    args: argparse.Namespace,
    state: str,
    comment: str,
    existing_comment: dict[str, Any] | None = None,
) -> int | None:
    """Report an already closed or merged PR, or the --dry-run plan.

    Returns the exit code when nothing is left to do, or None when the PR must be closed.
    """
    pr = args.pull_request
    if state in ("CLOSED", "MERGED"):
        result: dict[str, object] = {
            "success": True,
            "number": pr,
            "state": state,
            "action": "none",
            "message": f"PR already {state.lower()}",
        }
        if args.dry_run:
            result["dryRun"] = True
    elif args.dry_run:
        result = {
            "success": True,
            "number": pr,
            "state": state,
            "action": "would_close",
            "dryRun": True,
            "wouldComment": bool(comment) and existing_comment is None,
            "message": "Dry run: PR not closed",
        }
        if comment:
            result["commentDuplicate"] = existing_comment is not None
            if existing_comment is not None:
                result["existingCommentId"] = existing_comment.get("id")
    else:
        return None
    print(json.dumps(result, indent=2))
    return 0


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
        assert_valid_body_file(args.comment_file)
        try:
            comment = read_body_file_text(args.comment_file, allow_git_dir=True)
        except (OSError, ValueError) as exc:
            error_and_exit(f"Failed to read comment file {args.comment_file}: {exc}", 2)

    state_result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", "state"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if state_result.returncode != 0:
        output = state_result.stderr or state_result.stdout
        if is_pr_not_found(output):
            error_and_exit(f"PR #{pr} not found in {repo_flag}", 2)
        error_and_exit(f"Failed to get PR state: {output}", 3)

    state = json.loads(state_result.stdout).get("state", "")
    existing_comment = (
        _find_existing_closing_comment(owner, repo, pr, comment)
        if comment and state not in ("CLOSED", "MERGED")
        else None
    )

    reported = _report_noop_or_plan(args, state, comment, existing_comment)
    if reported is not None:
        return reported

    if comment and existing_comment is None:
        comment_result = subprocess.run(
            ["gh", "pr", "comment", str(pr), "--repo", repo_flag, "--body", comment],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if comment_result.returncode != 0:
            error_and_exit(
                f"Failed to post the closing comment on PR #{pr}: "
                f"{comment_result.stderr or comment_result.stdout}. "
                "The PR was NOT closed, so the explanation is never lost. "
                "Retry the same command once the API error clears.",
                3,
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

    result: dict[str, object] = {
        "success": True,
        "number": pr,
        "state": "CLOSED",
        "action": "closed",
        "message": "PR closed successfully",
    }
    if comment:
        result["commentPosted"] = existing_comment is None
        result["commentSkipped"] = existing_comment is not None
        if existing_comment is not None:
            result["existingCommentId"] = existing_comment.get("id")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
