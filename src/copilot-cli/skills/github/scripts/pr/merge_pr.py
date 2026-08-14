#!/usr/bin/env python3
# taste-lint: ignore file-size, CLI script keeps merge orchestration and output contract together.
# taste-lint: ignore complexity, CLI script keeps merge orchestration and output contract together.
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

from github_core.api import (
    assert_gh_authenticated,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)
from github_core.placeholder_identity import filter_coauthor_trailers

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

    Returns repository allow_* fields mapped to booleans.
    """
    result = subprocess.run(
        [
            "gh", "api", f"repos/{repo_flag}",
            "--jq", "{allow_merge_commit, allow_squash_merge, allow_rebase_merge}",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to query repository settings: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to decode JSON from GitHub API response: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("GitHub repository settings response must be an object")
    return {
        field: bool(data.get(field, False))
        for field in _STRATEGY_TO_REPO_FIELD.values()
    }


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
    repo_settings: dict[str, bool] | None,
    repo_flag: str,
    output_format: str,
) -> None:
    """Emit a JSON envelope and exit 1 when the strategy is disallowed.

    Regression guard for issue #2449: before this change, validation
    called error_and_exit which wrote plain text to stderr and produced
    no stdout, breaking consumers that piped to json.loads.

    When repo_settings is None, the caller supplied an explicit strategy and
    skipped REST settings discovery. GitHub rejects a disallowed method at
    merge time, and _handle_merge_failure surfaces a structured error.
    """
    if repo_settings is None:
        return
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


def _fetch_pr_state(
    pr: int,
    repo_flag: str,
    output_format: str,
) -> dict[str, Any]:
    """Fetch the PR state via gh; emit envelope and exit on failure."""
    pr_result = subprocess.run(
        [
            "gh", "pr", "view", str(pr), "--repo", repo_flag,
            "--json", "state,mergeable,mergeStateStatus,headRefName,headRefOid",
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if pr_result.returncode != 0:
        output = pr_result.stderr or pr_result.stdout
        if "not found" in output:
            _emit_error(f"PR #{pr} not found in {repo_flag}", 2, "NotFound", output_format, pr)
        _emit_error(f"Failed to get PR state: {output}", 3, "ApiError", output_format, pr)

    try:
        data = json.loads(pr_result.stdout)
    except json.JSONDecodeError:
        _emit_error(
            f"PR #{pr} state response was not valid JSON",
            3,
            "ApiError",
            output_format,
            pr,
        )
    if not isinstance(data, dict):
        _emit_error(
            f"PR #{pr} response was not a JSON object",
            3,
            "ApiError",
            output_format,
            pr,
        )
    return {str(key): value for key, value in data.items()}


def _reject_unknown_merge_state(
    pr_data: dict[str, Any],
    pr: int,
    output_format: str,
) -> None:
    """Reject a direct merge while GitHub is still calculating mergeability.

    Issue #2637: after a base update, GitHub reports mergeable=UNKNOWN and
    mergeStateStatus=UNKNOWN while it recalculates. The completion gate
    (.claude/skills/github/scripts/pr/test_pr_merge_ready.py) rejects this
    state with the reason "Merge status is being calculated" (its
    ``_evaluate_pr_state`` appends that reason for ``mergeable == "UNKNOWN"``),
    so a direct merge must reject it too instead of merging a PR its own gate
    just refused. Exit code 3 (ADR-035 external/transient): the caller can
    retry once GitHub settles. Callers that want auto-merge pass --auto, which
    skips this check and hands the decision to GitHub's own gate.
    """
    mergeable = pr_data.get("mergeable") or ""
    merge_state = pr_data.get("mergeStateStatus") or ""
    if mergeable != "UNKNOWN" and merge_state != "UNKNOWN":
        return
    _emit_error(
        f"PR #{pr} merge status is being calculated by GitHub "
        f"(mergeable={mergeable or 'UNKNOWN'}, "
        f"mergeStateStatus={merge_state or 'UNKNOWN'}). "
        "Retry once it settles, or use --auto to defer to GitHub's gate.",
        3,
        "ApiError",
        output_format,
        pr,
    )


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
        # Issue #2466: strip any placeholder Co-authored-by trailers before
        # passing the body to gh. The worktree-bootstrap reset (worktree_identity.py)
        # and pre-push guard (check_placeholder_identity.py) are the primary
        # defences; this sanitizer is a final backstop for the --body path.
        # When --body is empty, gh auto-assembles the squash message from commit
        # subjects; those commits are protected by the pre-push guard and the
        # worktree-bootstrap reset instead.
        sanitized_body = filter_coauthor_trailers(args.body)
        merge_args.extend(["--body", sanitized_body])
    return merge_args


def _rest_merge(
    pr: int,
    repo_flag: str,
    strategy: str,
    head_sha: str,
    subject: str,
    body: str,
) -> subprocess.CompletedProcess[str]:
    """Attempt a merge via the REST PUT endpoint.

    Issue #4362: the GraphQL ``mergePullRequest`` mutation used by ``gh pr
    merge`` can return "the base branch policy prohibits the merge" for PRs
    whose required checks are all SUCCESS and whose unresolved thread count
    is 0.  The REST endpoint enforces the same branch rules but accepts the
    same head SHA seconds later.  A single REST retry after a BLOCKED
    failure lets the authoritative server adjudicate instead of surfacing a
    GraphQL-specific refusal as a client-side error.
    """
    cmd = [
        "gh", "api", "-X", "PUT",
        f"repos/{repo_flag}/pulls/{pr}/merge",
        "-f", f"merge_method={strategy}",
        "-f", f"sha={head_sha}",
    ]
    if subject:
        cmd += ["-f", f"commit_title={subject}"]
    if body:
        cmd += ["-f", f"commit_message={body}"]
    return subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def _handle_merge_failure(
    merge_result: subprocess.CompletedProcess[str],
    pr: int,
    repo_flag: str,
    strategy: str,
    head_sha: str,
    subject: str,
    body: str,
    auto: bool,
    output_format: str,
) -> None:
    """Translate a non-zero gh-pr-merge return into a JSON error envelope.

    On a BLOCKED-keyword failure, retry once via the REST merge endpoint
    (issue #4362).  REST enforces the same branch rules as GraphQL but
    resolves the policy check differently; a 200 with ``merged: true``
    confirms the ruleset was satisfied and the GraphQL refusal was
    spurious.
    """
    output = merge_result.stderr or merge_result.stdout
    if any(kw in output for kw in ("not mergeable", "cannot be merged", "conflicts")):
        _emit_error(f"PR #{pr} is not mergeable: {output}", 6, "General", output_format, pr)
    if not auto and any(kw in output for kw in _BLOCKED_KEYWORDS):
        # GraphQL refused with a BLOCKED policy error; retry via REST once.
        rest_result = _rest_merge(pr, repo_flag, strategy, head_sha, subject, body)
        if rest_result.returncode == 0:
            try:
                rest_data = json.loads(rest_result.stdout)
            except json.JSONDecodeError:
                rest_data = {}
            if rest_data.get("merged"):
                return
        # REST also failed; surface the original GraphQL error.
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

    repo_settings: dict[str, bool] | None = None

    # Issue #4490: an explicit strategy does not need repository-settings
    # discovery. The merge endpoint remains the authority for whether GitHub
    # permits that strategy.
    if args.strategy is None:
        # No explicit strategy: must fetch repo settings to auto-pick one.
        # Wrap REST failures in a structured envelope so consumers can parse.
        try:
            repo_settings = get_allowed_merge_methods(repo_flag)
        except (RuntimeError, ValueError) as exc:
            _emit_error(str(exc), 3, "ApiError", output_format, pr)
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

    # Issue #2637: reject UNKNOWN mergeability on a direct merge. --auto is
    # exempt: it hands the merge decision to GitHub's own gate.
    if not args.auto:
        _reject_unknown_merge_state(pr_data, pr, output_format)

    merge_args = _build_merge_args(args, pr, repo_flag)
    merge_result = subprocess.run(
        merge_args,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if merge_result.returncode != 0:
        head_sha = pr_data.get("headRefOid") or ""
        sanitized_body = filter_coauthor_trailers(args.body) if args.body else ""
        _handle_merge_failure(
            merge_result,
            pr,
            repo_flag,
            args.strategy,
            head_sha,
            args.subject,
            sanitized_body,
            args.auto,
            output_format,
        )

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
