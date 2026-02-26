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
"""

from __future__ import annotations

import argparse
import json
import os
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
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    gh_graphql,
    resolve_repo_params,
)

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


def get_pr_node_id(owner: str, repo: str, pr_number: int) -> tuple[str, dict]:
    """Get PR node ID and current state. Returns (node_id, pr_data)."""
    try:
        data = gh_graphql(
            _PR_QUERY,
            {"owner": owner, "repo": repo, "number": pr_number},
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "Could not resolve" in msg:
            error_and_exit(f"PR #{pr_number} not found in {owner}/{repo}", 2)
        error_and_exit(f"Failed to get PR info: {msg}", 3)

    pr = data.get("repository", {}).get("pullRequest")
    if pr is None:
        error_and_exit(f"PR #{pr_number} not found", 2)

    return pr["id"], pr


def disable_auto_merge(
    owner: str, repo: str, pr_number: int, pr_id: str, pr_data: dict,
) -> int:
    """Disable auto-merge. Returns exit code."""
    if pr_data.get("autoMergeRequest") is None:
        print(f"Auto-merge is not enabled on PR #{pr_number}")
        output = {
            "Success": True,
            "Action": "NoChange",
            "PullRequest": pr_number,
            "AutoMergeEnabled": False,
            "Message": "Auto-merge was already disabled",
        }
        print(json.dumps(output, indent=2))
        return 0

    try:
        data = gh_graphql(_DISABLE_MUTATION, {"pullRequestId": pr_id})
    except RuntimeError as exc:
        error_and_exit(f"Failed to disable auto-merge: {exc}", 3)

    disabled = (
        data.get("disablePullRequestAutoMerge", {})
        .get("pullRequest", {})
        .get("autoMergeRequest")
        is None
    )

    output = {
        "Success": disabled,
        "Action": "Disabled",
        "PullRequest": pr_number,
        "AutoMergeEnabled": not disabled,
    }
    print(json.dumps(output, indent=2))

    if disabled:
        print(f"Auto-merge disabled for PR #{pr_number}")
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
) -> int:
    """Enable auto-merge. Returns exit code."""
    variables: dict = {
        "pullRequestId": pr_id,
        "mergeMethod": merge_method,
        "commitHeadline": commit_headline or "",
        "commitBody": commit_body or "",
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
        if "not mergeable" in msg:
            error_and_exit(
                "PR is not in a mergeable state. "
                "Check for conflicts or required reviews.",
                3,
            )
        error_and_exit(f"Failed to enable auto-merge: {msg}", 3)

    auto_merge = (
        data.get("enablePullRequestAutoMerge", {})
        .get("pullRequest", {})
        .get("autoMergeRequest")
    )
    enabled = auto_merge is not None

    output: dict = {
        "Success": enabled,
        "Action": "Enabled",
        "PullRequest": pr_number,
        "AutoMergeEnabled": enabled,
        "MergeMethod": auto_merge["mergeMethod"] if auto_merge else None,
        "EnabledAt": auto_merge["enabledAt"] if auto_merge else None,
    }
    print(json.dumps(output, indent=2))

    if enabled:
        print(f"Auto-merge enabled for PR #{pr_number}")
        print(f"  Method: {auto_merge['mergeMethod']}")
        print(f"  Enabled at: {auto_merge['enabledAt']}")
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
        "--pull-request", type=int, required=True,
        help="PR number",
    )

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--enable", action="store_true",
        help="Enable auto-merge",
    )
    action.add_argument(
        "--disable", action="store_true",
        help="Disable auto-merge",
    )

    parser.add_argument(
        "--merge-method",
        choices=["MERGE", "SQUASH", "REBASE"],
        default="SQUASH",
        help="Merge method (default: SQUASH)",
    )
    parser.add_argument(
        "--commit-headline", default="",
        help="Custom commit headline for squash/merge commits",
    )
    parser.add_argument(
        "--commit-body", default="",
        help="Custom commit body for squash/merge commits",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assert_gh_authenticated()

    resolved = resolve_repo_params(args.owner, args.repo)
    owner = resolved.owner
    repo = resolved.repo

    pr_id, pr_data = get_pr_node_id(owner, repo, args.pull_request)

    if args.disable:
        return disable_auto_merge(owner, repo, args.pull_request, pr_id, pr_data)

    return enable_auto_merge(
        owner,
        repo,
        args.pull_request,
        pr_id,
        args.merge_method,
        args.commit_headline,
        args.commit_body,
    )


if __name__ == "__main__":
    raise SystemExit(main())
