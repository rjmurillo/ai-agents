#!/usr/bin/env python3
"""Check whether an open PR already addresses a given issue (issue #2477).

Pre-flight guard against competing PRs: before an autonomous pipeline or an
interactive session opens a new PR for an issue, it should confirm no open PR
already claims that issue via a closing keyword. Two workers acting on the same
issue otherwise open duplicate PRs (the #2477 failure mode).

Detection is deterministic: list open PRs and match each body/title against the
GitHub closing-keyword forms for the issue number (Fixes/Closes/Resolves),
rather than a fragile free-text search.

Exit codes follow ADR-035:
    0 - No open PR claims implementation ownership (safe to proceed)
    1 - One or more open PRs claim implementation ownership (do not open a duplicate)
    2 - Config error (plugin lib path missing)
    3 - External error (gh/API failure)
    4 - Auth error (not authenticated)
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
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

# GitHub closing keywords identify PRs that claim implementation ownership. Issue
# #2477 originally included "Refs", but issue #4894 proved that diagnostic
# references can name unrelated blockers without implementing them.
_KEYWORDS = "close[sd]?|fix(e[sd])?|resolve[sd]?"
_GH_TIMEOUT_SECONDS = 30
_GIT_TIMEOUT_SECONDS = 10
_PullRequestPayload = dict[str, object]


def references_issue(text: str, issue: int, repo_slug: str = "") -> bool:
    """Return True when ``text`` claims ``issue`` via a closing keyword."""

    if not text:
        return False
    issue_ref = rf"#{issue}\b"
    if repo_slug:
        issue_ref = rf"(?:{re.escape(repo_slug)}#|#){issue}\b"
    pattern = re.compile(rf"(?i)\b(?:{_KEYWORDS})\b[\s:]*{issue_ref}")
    return bool(pattern.search(text))


def _run(cmd: list[str], *, timeout: int = _GH_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"{cmd[0]} timed out after {timeout} seconds") from err
    except OSError as err:
        raise RuntimeError(f"failed to run {cmd[0]}: {err}") from err


def current_branch() -> str:
    """Return the active branch name when available."""

    head_ref = os.environ.get("GITHUB_HEAD_REF")
    if head_ref:
        return head_ref
    try:
        result = _run(["git", "branch", "--show-current"], timeout=_GIT_TIMEOUT_SECONDS)
    except RuntimeError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def current_login() -> str:
    """Return the authenticated gh user login."""

    result = _run(["gh", "api", "user", "--jq", ".login"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api user failed")
    login = result.stdout.strip()
    if not login:
        raise RuntimeError("gh api user returned empty login")
    return login


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _iter_pull_requests(payload: object) -> list[_PullRequestPayload]:
    if not isinstance(payload, list):
        return []
    prs: list[_PullRequestPayload] = []
    for item in payload:
        if isinstance(item, dict):
            prs.append(item)
        elif isinstance(item, list):
            prs.extend(pr for pr in item if isinstance(pr, dict))
    return prs


def _head_ref(pr: _PullRequestPayload) -> str:
    head = pr.get("head")
    if isinstance(head, dict):
        return _as_text(head.get("ref"))
    return _as_text(pr.get("headRefName"))


def _author_login(pr: _PullRequestPayload) -> str:
    user = pr.get("user")
    if isinstance(user, dict):
        return _as_text(user.get("login"))
    return _as_text(pr.get("author"))


def _is_self_branch_pr(
    author_login: str,
    head_ref: str,
    *,
    current_branch_name: str,
    current_user_login: str,
) -> bool:
    """Return True when a PR is the current user's own current-branch PR.

    Suppression exists so the preflight does not flag the PR that belongs to the
    branch you are already on. It applies only when the current branch name is
    known and matches the PR head exactly.

    An empty ``current_branch_name`` (detached HEAD, or CI without
    ``GITHUB_HEAD_REF``) is NOT a match. Treating empty as a match suppressed
    every PR by the current user, so in a single-author repo the duplicate-PR
    guard reported zero coverage for every issue (issue #4965).
    """
    if not current_user_login or author_login != current_user_login:
        return False
    if not current_branch_name:
        return False
    return head_ref == current_branch_name


def filter_prs_for_issue(
    prs: object,
    issue: int,
    *,
    repo_slug: str = "",
    current_branch_name: str = "",
    current_user_login: str = "",
) -> list[_PullRequestPayload]:
    """Return open PRs whose title or body claims implementation of ``issue``.

    Pure matching logic, separated from the ``gh`` fetch so the suppression
    rules are deterministically testable (issue #4965).
    """
    matches: list[_PullRequestPayload] = []
    for pr in _iter_pull_requests(prs):
        head_ref = _head_ref(pr)
        author_login = _author_login(pr)
        text = f"{_as_text(pr.get('title'))}\n{_as_text(pr.get('body'))}"
        if not references_issue(text, issue, repo_slug=repo_slug):
            continue
        if _is_self_branch_pr(
            author_login,
            head_ref,
            current_branch_name=current_branch_name,
            current_user_login=current_user_login,
        ):
            continue
        matches.append({
            "number": pr.get("number"),
            "title": _as_text(pr.get("title")),
            "url": _as_text(pr.get("html_url") or pr.get("url")),
            "head": head_ref,
            "author": author_login,
        })
    return matches


def find_open_prs_for_issue(
    owner: str,
    repo: str,
    issue: int,
    *,
    current_branch_name: str = "",
    current_user_login: str = "",
) -> list[_PullRequestPayload]:
    """Fetch open PRs and return those claiming implementation of ``issue``."""

    result = _run(
        ["gh", "api", f"repos/{owner}/{repo}/pulls?state=open&per_page=100",
         "--paginate", "--slurp"],
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api pulls failed")
    try:
        prs = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as err:
        raise RuntimeError("could not parse gh api pulls output") from err
    return filter_prs_for_issue(
        prs,
        issue,
        repo_slug=f"{owner}/{repo}",
        current_branch_name=current_branch_name,
        current_user_login=current_user_login,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether an open PR already addresses an issue.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    fmt = get_output_format(args.output_format)

    try:
        matches = find_open_prs_for_issue(
            owner,
            repo,
            args.issue,
            current_branch_name=current_branch(),
            current_user_login=current_login(),
        )
    except RuntimeError as err:
        write_skill_error(
            str(err), 3, error_type="ApiError",
            output_format=fmt, script_name="check_existing_pr_for_issue.py",
        )
        raise SystemExit(3) from err

    data = {
        "issue": args.issue,
        "existing_pr_count": len(matches),
        "existing_prs": matches,
    }
    if matches:
        summary = ", ".join(f"#{m['number']}" for m in matches)
        write_skill_error(
            f"Issue #{args.issue} already has open PR(s): {summary}. "
            "Do not open a duplicate; coordinate on the existing PR.",
            1, error_type="General",
            output_format=fmt, script_name="check_existing_pr_for_issue.py",
            extra=data,
        )
        raise SystemExit(1)

    write_skill_output(
        data, output_format=fmt,
        human_summary=(
            f"No open PR claims implementation ownership of issue #{args.issue}; "
            "safe to proceed."
        ),
        status="PASS", script_name="check_existing_pr_for_issue.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
