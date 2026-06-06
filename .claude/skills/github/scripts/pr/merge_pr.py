#!/usr/bin/env python3
"""Merge a GitHub Pull Request.

Merges a PR using the specified strategy. Supports auto-merge
for PRs with pending checks.

When --strategy is omitted, the script consults the repository's
allowed merge methods and picks a default that satisfies repo policy
(squash preferred, then merge, then rebase). This avoids the
issue #2449 failure mode where a hard-coded 'merge' default
violated repos that disallow merge commits (e.g. rjmurillo/ai-agents
allows squash only).

All output goes through the standard skill envelope per ADR-056,
including error paths. Disallowed strategy, not-found PR, conflicts,
and other failures emit a JSON envelope on stdout (instead of plain
text on stderr), so consumers can pipe to json.loads without crashing.

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure)
    4 - Auth error
    6 - Not mergeable
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
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "merge_pr.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge a GitHub Pull Request.")
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--strategy", choices=["merge", "squash", "rebase"], default=None,
        help=(
            "Merge strategy. Omit to auto-pick from repo policy "
            "(squash > merge > rebase)."
        ),
    )
    parser.add_argument(
        "--delete-branch", action="store_true",
        help="Delete the head branch after merge",
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="Enable auto-merge (merge when checks pass)",
    )
    parser.add_argument("--subject", default="", help="Custom commit subject")
    parser.add_argument("--body", default="", help="Custom commit body")
    add_output_format_arg(parser)
    return parser


_STRATEGY_TO_REPO_FIELD = {
    "merge": "allow_merge_commit",
    "squash": "allow_squash_merge",
    "rebase": "allow_rebase_merge",
}

# Order matters: prefer squash (cleanest history), then merge, then rebase.
_STRATEGY_PREFERENCE = ("squash", "merge", "rebase")

_BLOCKED_KEYWORDS = ("BLOCKED", "branch protection", "required status check")


def get_allowed_merge_methods(repo_flag: str) -> dict[str, bool]:
    """Query repository settings for allowed merge methods.

    Returns a dict mapping strategy names to booleans.
    """
    result = subprocess.run(
        [
            "gh", "api", f"repos/{repo_flag}",
            "--jq", "{allow_merge_commit, allow_squash_merge, allow_rebase_merge}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        print(f"Error querying repository settings: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Failed to query repository settings: {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from GitHub API: {e}", file=sys.stderr)
        raise ValueError(f"Failed to decode JSON from GitHub API response: {e}") from e


def resolve_default_strategy(repo_settings: dict[str, bool]) -> str | None:
    """Pick a sensible default strategy from the repo's allowed methods.

    Returns the first preferred strategy that is allowed by the repo:
    squash > merge > rebase. Returns None if no strategy is allowed
    (caller should error with code 1).
    """
    for strategy in _STRATEGY_PREFERENCE:
        field = _STRATEGY_TO_REPO_FIELD[strategy]
        if repo_settings.get(field, False):
            return strategy
    return None


def validate_strategy(
    strategy: str,
    repo_settings: dict[str, bool],
    repo_flag: str,
    output_format: str,
) -> None:
    """Emit a JSON envelope and exit 1 when the strategy is disallowed.

    Regression guard for issue #2449: before this change, validation
    called error_and_exit which wrote plain text to stderr and produced
    no stdout, breaking consumers that piped to json.loads.
    """
    field = _STRATEGY_TO_REPO_FIELD.get(strategy)
    if field and repo_settings.get(field, False):
        return

    allowed = [
        name for name, fld in _STRATEGY_TO_REPO_FIELD.items()
        if repo_settings.get(fld, False)
    ]
    hint = f" Allowed: {', '.join(allowed)}." if allowed else ""
    write_skill_error(
        f"Strategy '{strategy}' is not allowed by {repo_flag}.{hint}",
        1,
        error_type="InvalidParams",
        output_format=output_format,
        script_name=_SCRIPT_NAME,
        extra={
            "pull_request": None,
            "strategy_requested": strategy,
            "allowed_strategies": allowed,
        },
    )
    raise SystemExit(1)


def _emit_error(
    message: str,
    code: int,
    error_type: str,
    output_format: str,
    pr: int,
) -> None:
    """Helper: emit envelope, then exit with the code."""
    write_skill_error(
        message,
        code,
        error_type=error_type,
        output_format=output_format,
        script_name=_SCRIPT_NAME,
        extra={"pull_request": pr},
    )
    raise SystemExit(code)


def _fetch_pr_state(pr: int, repo_flag: str, output_format: str) -> dict:
    """Fetch the PR state via gh; emit envelope and exit on failure."""
    pr_result = subprocess.run(
        [
            "gh", "pr", "view", str(pr), "--repo", repo_flag,
            "--json", "state,mergeable,mergeStateStatus,headRefName",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if pr_result.returncode != 0:
        output = pr_result.stderr or pr_result.stdout
        if "not found" in output:
            _emit_error(f"PR #{pr} not found in {repo_flag}", 2, "NotFound", output_format, pr)
        _emit_error(f"Failed to get PR state: {output}", 3, "ApiError", output_format, pr)

    return json.loads(pr_result.stdout)


def _build_merge_args(args: argparse.Namespace, pr: int, repo_flag: str) -> list[str]:
    """Assemble the gh pr merge argv from parsed args."""
    merge_args = [
        "gh", "pr", "merge", str(pr),
        "--repo", repo_flag,
        f"--{args.strategy}",
    ]
    if args.delete_branch:
        merge_args.append("--delete-branch")
    if args.auto:
        merge_args.append("--auto")
    if args.subject:
        merge_args.extend(["--subject", args.subject])
    if args.body:
        merge_args.extend(["--body", args.body])
    return merge_args


def _handle_merge_failure(
    merge_result: subprocess.CompletedProcess,
    pr: int,
    auto: bool,
    output_format: str,
) -> None:
    """Translate a non-zero gh-pr-merge return into a JSON error envelope."""
    output = merge_result.stderr or merge_result.stdout
    if any(kw in output for kw in ("not mergeable", "cannot be merged", "conflicts")):
        _emit_error(f"PR #{pr} is not mergeable: {output}", 6, "General", output_format, pr)
    if not auto and any(kw in output for kw in _BLOCKED_KEYWORDS):
        _emit_error(
            f"PR #{pr} is blocked by branch protection policy: {output}\n"
            "Hint: use --auto to enable auto-merge when checks pass.",
            6,
            "General",
            output_format,
            pr,
        )
    _emit_error(f"Failed to merge PR #{pr}: {output}", 3, "ApiError", output_format, pr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_format = args.output_format

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request
    repo_flag = f"{owner}/{repo}"

    repo_settings = get_allowed_merge_methods(repo_flag)

    if args.strategy is None:
        chosen = resolve_default_strategy(repo_settings)
        if chosen is None:
            _emit_error(
                f"No merge strategy allowed by {repo_flag}.",
                1,
                "InvalidParams",
                output_format,
                pr,
            )
        args.strategy = chosen

    validate_strategy(args.strategy, repo_settings, repo_flag, output_format)

    pr_data = _fetch_pr_state(pr, repo_flag, output_format)

    if pr_data.get("state") == "MERGED":
        write_skill_output(
            {
                "pull_request": pr,
                "number": pr,
                "state": "MERGED",
                "action": "none",
                "message": "PR already merged",
            },
            output_format=output_format,
            human_summary=f"PR #{pr} already merged",
            status="PASS",
            script_name=_SCRIPT_NAME,
        )
        return 0

    if pr_data.get("state") == "CLOSED":
        _emit_error(
            f"PR #{pr} is closed and cannot be merged",
            6,
            "General",
            output_format,
            pr,
        )

    merge_args = _build_merge_args(args, pr, repo_flag)
    merge_result = subprocess.run(
        merge_args, capture_output=True, text=True, timeout=60, check=False,
    )
    if merge_result.returncode != 0:
        _handle_merge_failure(merge_result, pr, args.auto, output_format)

    action = "auto-merge-enabled" if args.auto else "merged"
    state = "PENDING" if args.auto else "MERGED"
    message = "Auto-merge enabled" if args.auto else "PR merged successfully"

    write_skill_output(
        {
            "pull_request": pr,
            "number": pr,
            "state": state,
            "action": action,
            "strategy": args.strategy,
            "branch_deleted": args.delete_branch,
            "message": message,
        },
        output_format=output_format,
        human_summary=f"{message} (PR #{pr}, strategy={args.strategy})",
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
