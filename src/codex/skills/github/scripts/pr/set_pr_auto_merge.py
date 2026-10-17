#!/usr/bin/env python3
"""Enable or disable auto-merge for a GitHub Pull Request.

Uses GitHub GraphQL API to manage auto-merge settings. Auto-merge
automatically merges the PR once all required status checks pass
and required reviews are approved.

Requires auto-merge enabled in repository settings and write access.

Exit codes follow ADR-035:
    0 - Success
    1 - Operation failed or invalid parameters
    2 - PR not found
    3 - External error (API failure)
    4 - Auth error

``--output-format`` is the shared ADR-056 flag every sibling ``pr/`` script
accepts. ``json`` (and ``auto`` when stdout is not a terminal) prints only the
result object on stdout, so a pipe to ``jq`` parses. ``human`` prints only the
summary lines. The result object keeps its existing keys; it is not wrapped in
the ADR-056 envelope.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
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
    error_and_exit,
    gh_graphql,
    resolve_repo_params,
)
from github_core.not_found import is_pr_not_found
from github_core.output import add_output_format_arg, get_output_format
from github_core.placeholder_identity import filter_coauthor_trailers

# ---------------------------------------------------------------------------
# GraphQL queries and mutations
# ---------------------------------------------------------------------------

_PR_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            id
            number
            state
            autoMergeRequest {
                enabledAt
                mergeMethod
            }
        }
    }
}"""

_DISABLE_MUTATION = """\
mutation($pullRequestId: ID!) {
    disablePullRequestAutoMerge(input: {pullRequestId: $pullRequestId}) {
        pullRequest {
            id
            number
            autoMergeRequest {
                enabledAt
            }
        }
    }
}"""

_ENABLE_MUTATION = """\
mutation($pullRequestId: ID!, $mergeMethod: PullRequestMergeMethod!,\
 $commitHeadline: String, $commitBody: String) {
    enablePullRequestAutoMerge(input: {
        pullRequestId: $pullRequestId,
        mergeMethod: $mergeMethod,
        commitHeadline: $commitHeadline,
        commitBody: $commitBody
    }) {
        pullRequest {
            id
            number
            autoMergeRequest {
                enabledAt
                mergeMethod
            }
        }
    }
}"""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _emit_result(output: dict[str, Any], human_lines: list[str], output_format: str) -> None:
    """Print the result object (json) or the summary lines (human), never both."""
    if get_output_format(output_format) == "json":
        print(json.dumps(output, indent=2))
        return
    for line in human_lines:
        print(line)


def get_pr_node_id(owner: str, repo: str, pr_number: int) -> tuple[str, dict[str, Any]]:
    """Get PR node ID and current state. Returns (node_id, pr_data)."""
    try:
        data = gh_graphql(
            _PR_QUERY,
            {"owner": owner, "repo": repo, "number": pr_number},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if is_pr_not_found(msg):
            error_and_exit(f"PR #{pr_number} not found in {owner}/{repo}", 2)
        error_and_exit(f"Failed to get PR info: {msg}", 3)

    pr = data.get("repository", {}).get("pullRequest")
    if pr is None:
        error_and_exit(f"PR #{pr_number} not found", 2)

    return pr["id"], pr


def disable_auto_merge(
    owner: str,
    repo: str,
    pr_number: int,
    pr_id: str,
    pr_data: dict[str, Any],
    output_format: str = "auto",
) -> int:
    """Disable auto-merge. Returns exit code."""
    if pr_data.get("autoMergeRequest") is None:
        output = {
            "Success": True,
            "Action": "NoChange",
            "PullRequest": pr_number,
            "AutoMergeEnabled": False,
            "Message": "Auto-merge was already disabled",
        }
        _emit_result(output, [f"Auto-merge is not enabled on PR #{pr_number}"], output_format)
        return 0

    try:
        data = gh_graphql(_DISABLE_MUTATION, {"pullRequestId": pr_id})
    except RuntimeError as exc:
        error_and_exit(f"Failed to disable auto-merge: {exc}", 3)

    disabled = (
        data.get("disablePullRequestAutoMerge", {}).get("pullRequest", {}).get("autoMergeRequest")
        is None
    )

    output = {
        "Success": disabled,
        "Action": "Disabled",
        "PullRequest": pr_number,
        "AutoMergeEnabled": not disabled,
    }
    human = [f"Auto-merge disabled for PR #{pr_number}"] if disabled else []
    _emit_result(output, human, output_format)

    if disabled:
        return 0

    print(f"Failed to disable auto-merge for PR #{pr_number}", file=sys.stderr)
    return 1


def enable_auto_merge(
    owner: str,
    repo: str,
    pr_number: int,
    pr_id: str,
    merge_method: str,
    commit_headline: str,
    commit_body: str,
    output_format: str = "auto",
) -> int:
    """Enable auto-merge. Returns exit code."""
    # Issue #2466: strip placeholder Co-authored-by trailers from commit_body
    # before passing to GitHub. Primary defences are the worktree-bootstrap
    # reset and pre-push guard; this is the final backstop for the body path.
    # When commit_body is empty, GitHub auto-assembles from commit subjects,
    # which are protected by the pre-push guard and worktree-bootstrap reset.
    sanitized_body = filter_coauthor_trailers(commit_body) if commit_body else ""
    variables: dict[str, Any] = {
        "pullRequestId": pr_id,
        "mergeMethod": merge_method,
        "commitHeadline": commit_headline or "",
        "commitBody": sanitized_body,
    }

    try:
        data = gh_graphql(_ENABLE_MUTATION, variables)
    except RuntimeError as exc:
        msg = str(exc)
        if "Auto-merge is not allowed" in msg:
            error_and_exit(
                "Auto-merge is not enabled in repository settings. "
                "Enable it in Settings -> General -> Pull Requests.",
                3,
            )
        # Issue #2439: GitHub refuses auto-merge when
        # `mergeStateStatus == UNSTABLE` (e.g. a non-required check is
        # failing). The pr-autofix contract allows merging UNSTABLE PRs
        # when the failing checks are documented non-required ones, but
        # the auto-merge path cannot honor that. Direct the caller to
        # merge_pr.py, which performs an immediate merge and is the
        # documented fallback for this state.
        if "unstable status" in msg.lower():
            strategy = merge_method.lower()
            merge_script = shlex.quote(str(Path(__file__).resolve().parent / "merge_pr.py"))
            fallback = f"python3 {merge_script} --pull-request {pr_number} --strategy {strategy}"
            error_and_exit(
                "Cannot enable auto-merge: PR is in UNSTABLE merge state "
                "(non-required checks failing). GitHub blocks auto-merge "
                "for UNSTABLE PRs.\n"
                "If the failing checks are documented non-required "
                "failures, merge directly:\n"
                f"  {fallback}",
                3,
            )
        # Issue #2450: GitHub refuses auto-merge when
        # `mergeStateStatus == CLEAN` ("Pull request is in clean status").
        # CLEAN means every required check has passed, every required
        # review is approved, and there are no conflicts, so auto-merge
        # has nothing to wait on and is rejected. The correct action is
        # a direct merge via merge_pr.py. Surface the actionable fallback
        # instead of leaking the raw GraphQL prefix.
        if "clean status" in msg.lower():
            strategy = merge_method.lower()
            merge_script = shlex.quote(str(Path(__file__).resolve().parent / "merge_pr.py"))
            fallback = f"python3 {merge_script} --pull-request {pr_number} --strategy {strategy}"
            error_and_exit(
                "Cannot enable auto-merge: PR merge state is already "
                "satisfied (all required checks pass, no pending reviews, "
                "no conflicts). GitHub blocks auto-merge because there is "
                "nothing to wait on.\n"
                "Merge directly:\n"
                f"  {fallback}",
                3,
            )
        if "not mergeable" in msg:
            error_and_exit(
                "PR is not in a mergeable state. Check for conflicts or required reviews.",
                3,
            )
        error_and_exit(f"Failed to enable auto-merge: {msg}", 3)

    auto_merge = (
        data.get("enablePullRequestAutoMerge", {}).get("pullRequest", {}).get("autoMergeRequest")
    )
    enabled = auto_merge is not None

    output: dict[str, Any] = {
        "Success": enabled,
        "Action": "Enabled",
        "PullRequest": pr_number,
        "AutoMergeEnabled": enabled,
        "MergeMethod": auto_merge["mergeMethod"] if auto_merge else None,
        "EnabledAt": auto_merge["enabledAt"] if auto_merge else None,
    }
    human = (
        [
            f"Auto-merge enabled for PR #{pr_number}",
            f"  Method: {auto_merge['mergeMethod']}",
            f"  Enabled at: {auto_merge['enabledAt']}",
        ]
        if auto_merge
        else []
    )
    _emit_result(output, human, output_format)

    if enabled:
        return 0

    print(f"Failed to enable auto-merge for PR #{pr_number}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Enable or disable auto-merge for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="PR number",
    )

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--enable",
        action="store_true",
        help="Enable auto-merge",
    )
    action.add_argument(
        "--disable",
        action="store_true",
        help="Disable auto-merge",
    )

    parser.add_argument(
        "--merge-method",
        "--strategy",
        dest="merge_method",
        type=str.upper,
        choices=["MERGE", "SQUASH", "REBASE"],
        default="SQUASH",
        help="Merge method (default SQUASH). --strategy alias; case-insensitive (#2684).",
    )
    parser.add_argument(
        "--commit-headline",
        default="",
        help="Custom commit headline for squash/merge commits",
    )
    parser.add_argument(
        "--commit-body",
        default="",
        help="Custom commit body for squash/merge commits",
    )
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    pr_id, pr_data = get_pr_node_id(owner, repo, args.pull_request)

    if args.disable:
        return disable_auto_merge(
            owner, repo, args.pull_request, pr_id, pr_data, args.output_format
        )

    return enable_auto_merge(
        owner,
        repo,
        args.pull_request,
        pr_id,
        args.merge_method,
        args.commit_headline,
        args.commit_body,
        args.output_format,
    )


if __name__ == "__main__":
    raise SystemExit(main())
