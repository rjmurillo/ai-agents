#!/usr/bin/env python3
"""Fetch the review submissions (verdicts) on a GitHub Pull Request.

``get_pr_review_comments.py`` returns line-level comments and
``get_pr_review_threads.py`` returns threaded conversations, but neither
returns the top-level review object that carries the verdict. ``APPROVED`` and
``CHANGES_REQUESTED`` bodies were therefore reachable only through a raw
``gh api`` call (issue #4378). This script pages
``repos/{owner}/{repo}/pulls/{n}/reviews`` and emits the ADR-056 envelope with
``Data.reviews`` as a list of
``{id, nodeId, author, authorId, authorObserved, state, body, submittedAt,
url, commitId}``.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - File not found / config error
    3 - External error (API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

# Two rungs, both portable. The plugin-root variables win when the host exports
# them; otherwise walk up from this file, which lands on the lib directory of
# whichever plugin root ships this copy. Sibling scripts carry a third rung
# built from a hard-coded ".claude/lib" under GITHUB_WORKSPACE; that rung names
# a layout only the upstream checkout has, and the walk-up already covers the
# case it was there for.
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

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    gh_api_paginated,
    resolve_repo_params,
)
from github_core.bot_config import canonicalize_login  # noqa: E402
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT = "get_pr_reviews.py"
_VALID_STATES = ("APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch the review submissions (verdicts) on a GitHub PR.",
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
        "--state",
        default="",
        help=f"Filter by review state. One of: {', '.join(_VALID_STATES)}",
    )
    add_output_format_arg(parser)
    return parser


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    """Reshape one REST review object into the skill's stable field names.

    ``author`` is canonicalized so the same integration reporting under
    several logins reads as one actor, matching get_pr_reviewers.py. The
    observed login is kept in ``authorObserved`` for audit.
    """
    user = item.get("user")
    observed = user.get("login") if isinstance(user, dict) else None
    author_id = user.get("id") if isinstance(user, dict) else None
    if not isinstance(author_id, int):
        author_id = None
    return {
        "id": item.get("id"),
        "nodeId": item.get("node_id"),
        "author": canonicalize_login(observed, author_id) if observed else None,
        "authorId": author_id,
        "authorObserved": observed,
        "state": item.get("state"),
        "body": item.get("body") or "",
        "submittedAt": item.get("submitted_at"),
        "url": item.get("html_url"),
        "commitId": item.get("commit_id"),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    pr: int = args.pull_request

    state_filter = args.state.strip().upper()
    if state_filter and state_filter not in _VALID_STATES:
        write_skill_error(
            f"Invalid --state {args.state!r}. Valid states: {', '.join(_VALID_STATES)}",
            1,
            error_type="InvalidParams",
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"pull_request": pr, "state": args.state},
        )
        return 1

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    raw = gh_api_paginated(f"repos/{owner}/{repo}/pulls/{pr}/reviews")
    reviews = [_normalize(r) for r in raw]
    if state_filter:
        reviews = [r for r in reviews if r["state"] == state_filter]

    data = {
        "pull_request": pr,
        "owner": owner,
        "repo": repo,
        "count": len(reviews),
        "reviews": reviews,
    }
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"PR #{pr}: {len(reviews)} review submission(s)",
        status="PASS",
        script_name=_SCRIPT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
