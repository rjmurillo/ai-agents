#!/usr/bin/env python3
"""List GitHub Issues with optional filters.

Enumerates issues in a repository with filtering capabilities:
- State (open, closed, all)
- Labels (comma-separated or single label)
- Author
- Assignee
- Search query
- Result limit

Emits the standard skill envelope. In JSON mode, stdout is:
``{"Success": bool, "Data": {"issues": [...], "count": int}, ...}``.
Failure paths emit the same envelope with ``Error`` populated.

Mirrors the PR-side ``get_pull_requests.py`` precedent, providing a
script that can actually list issues (see issue #2110).

Exit codes follow ADR-035:
    0 - Success
    2 - Config / argument error
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
from typing import Any, NoReturn

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
    GhAuthStatus,
    assert_gh_authenticated,
    classify_gh_failure_text,
    is_auth_failure_text,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List GitHub Issues with optional filters.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--state", choices=["open", "closed", "all"], default="open",
        help="Issue state filter (default: open)",
    )
    parser.add_argument(
        "--label", default="",
        help="Filter by label(s). Comma-separated for multiple.",
    )
    parser.add_argument(
        "--author", default="", help="Filter by issue author username",
    )
    parser.add_argument(
        "--assignee", default="",
        help="Filter by assignee username (use '@me' for self).",
    )
    parser.add_argument(
        "--search", default="",
        help="GitHub search query (e.g. 'fix auth is:open'). "
             "When used, --state/--label/--author/--assignee are ignored.",
    )
    parser.add_argument(
        "--limit", type=int, default=30,
        help="Max number of issues to return (1-1000, default: 30)",
    )
    add_output_format_arg(parser)
    return parser


def _exit_with_error(
    message: str,
    exit_code: int,
    fmt: str,
    error_type: str = "General",
) -> NoReturn:
    write_skill_error(
        message,
        exit_code,
        error_type=error_type,
        output_format=fmt,
        script_name="list_issues.py",
    )
    raise SystemExit(exit_code)


def _resolve_repo(args: argparse.Namespace, fmt: str) -> tuple[str, str]:
    try:
        assert_gh_authenticated()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 4
        _exit_with_error(
            "GitHub CLI (gh) is not installed or not authenticated. Run 'gh auth login' first.",
            code,
            fmt,
            "AuthError",
        )
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            resolved = resolve_repo_params(args.owner, args.repo)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        message = stderr.getvalue().strip() or "Could not resolve repository parameters."
        _exit_with_error(
            message,
            code,
            fmt,
            "InvalidParams",
        )
    return resolved.owner, resolved.repo


def _build_issue_list_args(args: argparse.Namespace, repo_flag: str) -> list[str]:
    list_args = [
        "gh", "issue", "list",
        "--repo", repo_flag,
        "--limit", str(args.limit),
        "--json", "number,title,state,labels,assignees,author,url,createdAt,updatedAt",
    ]

    if args.search:
        # gh issue list --search ignores --state, --label, --author,
        # --assignee. Only pass --search to avoid misleading behavior.
        list_args.extend(["--search", args.search])
    else:
        # Forward every state, including 'all'. Omitting --state makes
        # gh fall back to its open-only default, which silently drops
        # closed issues when the caller asked for --state all.
        list_args.extend(["--state", args.state])

        if args.label:
            labels = [lbl.strip() for lbl in args.label.split(",") if lbl.strip()]
            for lbl in labels:
                list_args.extend(["--label", lbl])

        if args.author:
            list_args.extend(["--author", args.author])

        if args.assignee:
            list_args.extend(["--assignee", args.assignee])

    return list_args


def _verify_empty_issue_result(fmt: str) -> None:
    """Confirm GraphQL is serving before trusting an empty issue list."""
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", "query={viewer{login}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _exit_with_error(
            "Could not verify empty issue list: GraphQL probe timed out.",
            3,
            fmt,
            "Timeout",
        )
    except FileNotFoundError:
        _exit_with_error("gh CLI not found on PATH.", 3, fmt, "ApiError")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip() or "no output"
        status = classify_gh_failure_text(detail)
        if status in (GhAuthStatus.RATE_LIMITED, GhAuthStatus.SECONDARY_RATE_LIMITED):
            _exit_with_error(
                f"Could not verify empty issue list: GraphQL rate limit exhausted: {detail}",
                3,
                fmt,
                "RateLimitError",
            )
        _exit_with_error(
            f"Could not verify empty issue list: GraphQL probe failed: {detail}",
            3,
            fmt,
            "ApiError",
        )


def _run_issue_list(list_args: list[str], fmt: str) -> list[object]:
    try:
        result = subprocess.run(
            list_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _exit_with_error("Timed out waiting for gh issue list.", 3, fmt, "Timeout")
    except FileNotFoundError:
        _exit_with_error("gh CLI not found on PATH.", 3, fmt, "ApiError")

    if result.returncode != 0:
        detail = result.stderr or result.stdout
        status = classify_gh_failure_text(detail)
        if status in (GhAuthStatus.RATE_LIMITED, GhAuthStatus.SECONDARY_RATE_LIMITED):
            _exit_with_error(
                f"GraphQL rate limit exhausted: {detail.strip()}",
                3,
                fmt,
                "RateLimitError",
            )
        if is_auth_failure_text(detail):
            _exit_with_error(
                f"Authentication failure: {detail.strip()}",
                4,
                fmt,
                "AuthError",
            )
        _exit_with_error(
            f"Failed to list issues: {detail}",
            3,
            fmt,
            "ApiError",
        )

    try:
        issues = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        _exit_with_error(
            f"Failed to parse JSON response from gh: {exc}",
            3,
            fmt,
            "ApiError",
        )

    if not isinstance(issues, list):
        _exit_with_error(
            f"Expected a JSON array from gh, got {type(issues).__name__}.",
            3,
            fmt,
            "ApiError",
        )

    if not issues:
        _verify_empty_issue_result(fmt)

    return issues


def _format_issue(issue: dict[str, Any]) -> dict[str, object]:
    return {
        "number": issue.get("number"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "labels": [
            lbl.get("name")
            for lbl in (issue.get("labels") or [])
            if isinstance(lbl, dict)
        ],
        "assignees": [
            assignee.get("login")
            for assignee in (issue.get("assignees") or [])
            if isinstance(assignee, dict)
        ],
        "author": (issue.get("author") or {}).get("login"),
        "url": issue.get("url"),
        "createdAt": issue.get("createdAt"),
        "updatedAt": issue.get("updatedAt"),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    if not 1 <= args.limit <= 1000:
        _exit_with_error(
            "Limit must be between 1 and 1000.",
            2,
            fmt,
            "InvalidParams",
        )

    owner, repo = _resolve_repo(args, fmt)
    issues = _run_issue_list(_build_issue_list_args(args, f"{owner}/{repo}"), fmt)
    output = [
        _format_issue(issue) for issue in issues if isinstance(issue, dict)
    ]

    write_skill_output(
        {"issues": output, "count": len(output)},
        output_format=fmt,
        human_summary=f"{len(output)} issue(s)",
        status="PASS",
        script_name="list_issues.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
