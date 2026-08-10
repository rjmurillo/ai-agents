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
import re
import subprocess
import sys
import time

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
    resolve_repo_params,
)
from github_core.output import (
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
ISSUE_COMMENT_PAGE_PACE_SECONDS = 3.0
ISSUE_COMMENT_REFUSAL_BACKOFF_SECONDS = (300.0, 600.0)
_RETRYABLE_COMMENT_FETCH_ERROR = re.compile(
    r"rate limit|secondary rate|abuse detection|\bHTTP\s+(429|500|502|503|504)\b",
    re.IGNORECASE,
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


def _comment_page_error_text(
    result: subprocess.CompletedProcess[str],
    page: int,
) -> str:
    message = result.stderr.strip() or result.stdout.strip()
    if message:
        return message
    return (
        "gh api exited with return code "
        f"{result.returncode} while fetching issue comment page {page} "
        "and no error output"
    )


def _run_comment_page(
    owner: str,
    repo: str,
    issue: int,
    page: int,
) -> subprocess.CompletedProcess[str]:
    endpoint = f"repos/{owner}/{repo}/issues/{issue}/comments?per_page=100&page={page}"
    attempts = len(ISSUE_COMMENT_REFUSAL_BACKOFF_SECONDS) + 1
    for attempt in range(attempts):
        try:
            result = subprocess.run(
                ["gh", "api", endpoint],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired:
            result = subprocess.CompletedProcess(
                ["gh", "api", endpoint],
                3,
                stdout="",
                stderr=f"Timed out fetching comments for issue #{issue}",
            )
        if result.returncode == 0:
            return result

        error_text = _comment_page_error_text(result, page)
        if attempt >= len(
            ISSUE_COMMENT_REFUSAL_BACKOFF_SECONDS
        ) or not _RETRYABLE_COMMENT_FETCH_ERROR.search(error_text):
            return result

        delay = ISSUE_COMMENT_REFUSAL_BACKOFF_SECONDS[attempt]
        print(
            f"GitHub refused issue comment page {page}; retrying in {delay:.0f}s",
            file=sys.stderr,
        )
        time.sleep(delay)

    raise RuntimeError("unreachable issue comment retry loop")


def _comment_page_items(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return [payload] if isinstance(payload, dict) else []
    comments: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, list):
            comments.extend(_comment_page_items(item))
        elif isinstance(item, dict):
            comments.append(item)
    return comments


def _fetch_comments(owner: str, repo: str, issue: int, fmt: str) -> list[dict[str, object]]:
    comments: list[dict[str, object]] = []
    page = 1
    while True:
        result = _run_comment_page(owner, repo, issue, page)
        if result.returncode != 0:
            error_str = _comment_page_error_text(result, page)
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

        items = _comment_page_items(payload)
        if not items:
            break
        comments.extend(items)
        if len(items) < 100:
            break
        time.sleep(ISSUE_COMMENT_PAGE_PACE_SECONDS)
        page += 1
    return comments


def _normalize(item: dict[str, object]) -> dict[str, object]:
    user = item.get("user")
    author = user.get("login") if isinstance(user, dict) else None
    return {
        "id": item.get("id"),
        "node_id": item.get("node_id"),
        "author": author,
        "createdAt": item.get("created_at"),
        "updatedAt": item.get("updated_at"),
        "body": item.get("body") or "",
        "url": item.get("html_url"),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    issue: int = args.issue

    if args.limit < 0:
        write_skill_error(
            "--limit must be 0 or greater",
            1,
            error_type="InvalidParams",
            output_format=fmt,
            script_name=_SCRIPT,
            extra={"issue": issue, "limit": args.limit},
        )
        return 1

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    raw = _fetch_comments(owner, repo, issue, fmt)
    comments = [_normalize(c) for c in raw]
    if args.limit > 0:
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
