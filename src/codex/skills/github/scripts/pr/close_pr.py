#!/usr/bin/env python3
"""Close a GitHub Pull Request.

Closes a PR with optional comment explaining the reason.
Supports idempotency: returns success if already closed.
A failed closing comment stops the run with exit 3 before the close call.
A retry skips posting when the same author already left an identical comment, then
closes. A token that cannot call GET /user (an Actions installation token) matches
an identical comment from any bot account instead. The skip is by body, not by
time: closing, reopening, and closing again with the same text posts it only once.
The comment lookup also runs under --dry-run, so a lookup failure exits 3 there too.
Success output adds commentPosted, commentSkipped, and existingCommentId.

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
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))
_script_dir = os.path.dirname(__file__)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from close_pr_steps import close_pull_request, post_closing_comment, pr_state, read_comment
from github_core.api import assert_gh_authenticated, resolve_repo_params
from pr_comment_lookup import find_existing_comment

_HELP_EPILOG = """\
examples:
  %(prog)s --pull-request 123
  %(prog)s --pull-request 123 --comment "Superseded by #130"

exit codes:
  0  success
  2  not found
  3  external error (API failure, including a failed closing comment or comment lookup: the PR stays open)
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
    parser.add_argument(
        "--comment",
        default="",
        help="Comment to post before closing; skipped when an identical one by the same author exists",
    )
    parser.add_argument(
        "--comment-file",
        default="",
        help="File containing comment body",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Read the PR state and existing comments, and report what would happen; "
            "comment and close nothing"
        ),
    )
    return parser


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


def _print_closed_envelope(pr: int, comment: str, existing_comment: dict[str, Any] | None) -> int:
    """Print the success envelope for a close and return 0."""
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request
    repo_flag = f"{owner}/{repo}"

    comment = read_comment(args.comment, args.comment_file)
    state = pr_state(pr, repo_flag)
    existing_comment = None
    if comment and state not in ("CLOSED", "MERGED"):
        existing_comment = find_existing_comment(owner, repo, pr, comment)

    reported = _report_noop_or_plan(args, state, comment, existing_comment)
    if reported is not None:
        return reported

    if comment and existing_comment is None:
        post_closing_comment(pr, repo_flag, comment)

    close_pull_request(pr, repo_flag)
    return _print_closed_envelope(pr, comment, existing_comment)


if __name__ == "__main__":
    raise SystemExit(main())
