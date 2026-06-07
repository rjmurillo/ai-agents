#!/usr/bin/env python3
"""Claim an issue by self-assigning, refusing if already claimed (issue #2477).

Pre-flight coordination for the competing-PR failure mode: a worker claims an
issue before starting development. If another login already holds the issue, the
claim is refused so two workers do not develop the same issue in parallel.

Exit codes follow ADR-035:
    0 - Claimed (now assigned to the current user) or already held by current user
    1 - Already claimed by a different login (do not start; coordinate)
    2 - Config error (plugin lib path missing)
    3 - External error (gh/API failure)
    4 - Auth error (not authenticated)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("COPILOT_PLUGIN_ROOT")
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


_GH_TIMEOUT_SECONDS = 30


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(
            f"{cmd[0]} timed out after {_GH_TIMEOUT_SECONDS} seconds"
        ) from err
    except OSError as err:
        raise RuntimeError(f"failed to run {cmd[0]}: {err}") from err


def current_login() -> str:
    """Return the authenticated gh user login."""

    result = _run(["gh", "api", "user", "--jq", ".login"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api user failed")
    login = result.stdout.strip()
    if not login:
        raise RuntimeError("gh api user returned empty login")
    return login


def issue_assignees(owner: str, repo: str, issue: int) -> list[str]:
    """Return the current assignee logins for the issue."""

    result = _run(
        ["gh", "issue", "view", str(issue), "--repo", f"{owner}/{repo}",
         "--json", "assignees"],
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh issue view failed")
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as err:
        raise RuntimeError("could not parse gh issue view output") from err
    assignees_value = data.get("assignees")
    assignees = [] if assignees_value is None else assignees_value
    if not isinstance(assignees, list):
        raise RuntimeError("gh issue view returned invalid assignees")
    return [
        login
        for assignee in assignees
        if isinstance(assignee, dict)
        for login in [assignee.get("login")]
        if isinstance(login, str) and login
    ]


def write_already_claimed(
    issue: int,
    assignees: list[str],
    others: list[str],
    fmt: str,
) -> None:
    write_skill_error(
        f"Issue #{issue} already claimed by {', '.join(others)}. "
        "Do not start in parallel; coordinate with the assignee.",
        1, error_type="General",
        output_format=fmt, script_name="claim_issue.py",
        extra={"issue": issue, "assignees": assignees},
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Self-assign an issue, refusing if already claimed by another login.",
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
        me = current_login()
        assignees = issue_assignees(owner, repo, args.issue)
    except RuntimeError as err:
        write_skill_error(
            str(err), 3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
        )
        raise SystemExit(3) from err

    others = [a for a in assignees if a != me]
    if others:
        write_already_claimed(args.issue, assignees, others, fmt)
        raise SystemExit(1)

    if me and me in assignees:
        write_skill_output(
            {"issue": args.issue, "assignees": assignees, "claimed": me},
            output_format=fmt,
            human_summary=f"Issue #{args.issue} already held by {me}.",
            status="PASS", script_name="claim_issue.py",
        )
        return 0

    try:
        assign = _run(
            ["gh", "issue", "edit", str(args.issue), "--repo", f"{owner}/{repo}",
             "--add-assignee", "@me"],
        )
    except RuntimeError as err:
        write_skill_error(
            str(err),
            3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
        )
        raise SystemExit(3) from err
    if assign.returncode != 0:
        write_skill_error(
            assign.stderr.strip() or "gh issue edit failed",
            3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
        )
        raise SystemExit(3)

    try:
        assignees_after_claim = issue_assignees(owner, repo, args.issue)
    except RuntimeError as err:
        write_skill_error(
            str(err), 3, error_type="ApiError",
            output_format=fmt, script_name="claim_issue.py",
        )
        raise SystemExit(3) from err
    others_after_claim = [a for a in assignees_after_claim if a != me]
    if others_after_claim:
        write_already_claimed(args.issue, assignees_after_claim, others_after_claim, fmt)
        raise SystemExit(1)

    write_skill_output(
        {"issue": args.issue, "claimed": me or "@me"},
        output_format=fmt,
        human_summary=f"Claimed issue #{args.issue} for {me or '@me'}.",
        status="PASS", script_name="claim_issue.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
