#!/usr/bin/env python3
"""Fetch the comment thread (discourse) of a GitHub Issue.

``get_issue_context.py`` returns issue metadata but no comments, so an agent
asked to "review the discourse" before triaging could not read prior triage
decisions, maintainer keep-open calls, or bot plans through the skill (Issue
#2475). This script fills that gap: it pages through
``repos/{owner}/{repo}/issues/{n}/comments`` and emits the standard ADR-056
envelope with ``Data.comments`` as a list of
``{author, createdAt, updatedAt, body, url}``.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - File not found / config error
    3 - External error (API failure)
    4 - Auth error (not authenticated)
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
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (  # noqa: E402
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT = "get_issue_comments.py"
_AUTH_ERROR_MARKERS = (
    "credential",
    "not logged in",
    "bad credentials",
    "could not authenticate",
    "authentication",
    "requires authentication",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch the comment thread of a GitHub Issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Return only the most recent N comments (0 = all, default).",
    )
    add_output_format_arg(parser)
    return parser


def _is_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _AUTH_ERROR_MARKERS)


def _exit_code_for(message: str, *, not_found: bool) -> tuple[int, str]:
    if not_found:
        return 2, "NotFound"
    if _is_auth_error(message):
        return 4, "AuthError"
    return 3, "ApiError"


def _fetch_comments(owner: str, repo: str, issue: int, fmt: str) -> list[dict[str, object]]:
    """Page through the issue's comments via gh api. Raises SystemExit on error."""
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/issues/{issue}/comments?per_page=100",
            "--paginate",
            "--slurp",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        error_str = result.stderr.strip() or result.stdout.strip()
        not_found = "Could not resolve" in error_str or "not found" in error_str.lower()
        code, error_type = _exit_code_for(error_str, not_found=not_found)
        write_skill_error(
            f"Failed to fetch comments for issue #{issue}: {error_str}",
            code,
            error_type=error_type,
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"issue": issue},
        )
        raise SystemExit(code)
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        write_skill_error(
            f"Failed to parse comments for issue #{issue}: {exc}",
            3,
            error_type="ApiError",
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"issue": issue},
        )
        raise SystemExit(3) from exc
    # --slurp wraps each page's array in an outer list; flatten one level.
    pages = payload if isinstance(payload, list) else [payload]
    comments: list[dict[str, object]] = []
    for page in pages:
        items = page if isinstance(page, list) else [page]
        for item in items:
            if isinstance(item, dict):
                comments.append(item)
    return comments


def _normalize(item: dict[str, object]) -> dict[str, object]:
    user = item.get("user")
    author = user.get("login") if isinstance(user, dict) else None
    return {
        "author": author,
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
        "body": item.get("body") or "",
        "url": item.get("html_url"),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    issue: int = args.issue

    raw = _fetch_comments(owner, repo, issue, fmt)
    comments = [_normalize(c) for c in raw]
    if args.limit and args.limit > 0:
        comments = comments[-args.limit :]

    data = {
        "issue": issue,
        "owner": owner,
        "repo": repo,
        "count": len(comments),
        "comments": comments,
    }
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"Issue #{issue}: {len(comments)} comment(s)",
        status="PASS",
        script_name=_SCRIPT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
