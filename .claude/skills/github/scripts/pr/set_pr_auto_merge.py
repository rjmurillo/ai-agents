#!/usr/bin/env python3
"""Enable or disable auto-merge on a GitHub Pull Request.

Uses GraphQL mutations to toggle auto-merge with configurable merge method,
commit headline, and commit body.

Exit codes (ADR-035):
    0 = Success
    1 = Invalid parameters
    2 = PR not found
    3 = API error
    4 = Not authenticated
    6 = Not mergeable (branch protections or status checks prevent auto-merge)
"""

import argparse
import json
import os
import subprocess
import sys

_lib_dir = os.path.join(
    os.environ.get("CLAUDE_PLUGIN_ROOT", os.path.join(os.getcwd(), ".claude")),
    "skills", "github", "lib",
)
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    assert_gh_authenticated,
    gh_graphql,
    resolve_repo_params,
    write_error_and_exit,
)

ENABLE_MUTATION = """
mutation(
  $pullRequestId: ID!,
  $mergeMethod: PullRequestMergeMethod!,
  $commitHeadline: String,
  $commitBody: String
) {
    enablePullRequestAutoMerge(input: {
        pullRequestId: $pullRequestId
        mergeMethod: $mergeMethod
        commitHeadline: $commitHeadline
        commitBody: $commitBody
    }) {
        pullRequest {
            number
            autoMergeRequest {
                mergeMethod
                enabledAt
            }
        }
    }
}
"""

DISABLE_MUTATION = """
mutation($pullRequestId: ID!) {
    disablePullRequestAutoMerge(input: {
        pullRequestId: $pullRequestId
    }) {
        pullRequest {
            number
        }
    }
}
"""


def get_pr_node_id(owner: str, repo: str, pr: int) -> str:
    """Get the GraphQL node ID for a PR."""
    result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", f"{owner}/{repo}", "--json", "id"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if "not found" in result.stderr.lower() or "Could not resolve" in result.stderr:
            write_error_and_exit(f"PR #{pr} not found in {owner}/{repo}", 2)
        write_error_and_exit(f"Failed to fetch PR: {result.stderr}", 3)

    data = json.loads(result.stdout)
    node_id: str | None = data.get("id")
    if not node_id:
        write_error_and_exit(f"PR #{pr} has no node ID", 3)
        # write_error_and_exit calls sys.exit; this line is unreachable
        raise SystemExit(3)
    return node_id


def enable_auto_merge(
    node_id: str, merge_method: str,
    commit_headline: str | None, commit_body: str | None,
) -> dict:
    """Enable auto-merge on a PR via GraphQL mutation."""
    variables: dict = {
        "pullRequestId": node_id,
        "mergeMethod": merge_method,
    }
    if commit_headline:
        variables["commitHeadline"] = commit_headline
    if commit_body:
        variables["commitBody"] = commit_body

    return gh_graphql(ENABLE_MUTATION, variables)


def disable_auto_merge(node_id: str) -> dict:
    """Disable auto-merge on a PR via GraphQL mutation."""
    return gh_graphql(DISABLE_MUTATION, {"pullRequestId": node_id})


def main() -> None:
    parser = argparse.ArgumentParser(description="Enable or disable PR auto-merge")
    parser.add_argument("--owner", help="Repository owner")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--pull-request", type=int, required=True, help="PR number")

    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--enable", action="store_true", help="Enable auto-merge")
    action_group.add_argument("--disable", action="store_true", help="Disable auto-merge")

    parser.add_argument(
        "--merge-method", choices=["MERGE", "SQUASH", "REBASE"],
        default="SQUASH", help="Merge method (default: SQUASH, only with --enable)",
    )
    parser.add_argument("--commit-headline", help="Custom commit headline (only with --enable)")
    parser.add_argument("--commit-body", help="Custom commit body (only with --enable)")
    args = parser.parse_args()

    # Validate enable-only options are not used with disable
    if args.disable:
        if args.commit_headline or args.commit_body:
            write_error_and_exit(
                "--commit-headline and --commit-body can only be used with --enable", 1
            )

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved["owner"], resolved["repo"]

    node_id = get_pr_node_id(owner, repo, args.pull_request)

    try:
        if args.enable:
            enable_auto_merge(node_id, args.merge_method, args.commit_headline, args.commit_body)
            action_label = "enabled"
        else:
            disable_auto_merge(node_id)
            action_label = "disabled"
    except RuntimeError as e:
        error_msg = str(e).lower()
        if "not in a mergeable state" in error_msg or "auto-merge is not allowed" in error_msg:
            write_error_and_exit(
                f"PR #{args.pull_request} is not eligible for auto-merge: {e}", 6
            )
        write_error_and_exit(f"GraphQL error: {e}", 3)
    except Exception as e:
        write_error_and_exit(f"API request failed: {e}", 3)

    output = {
        "Success": True,
        "PullRequest": args.pull_request,
        "Owner": owner,
        "Repo": repo,
        "AutoMerge": action_label,
        "MergeMethod": args.merge_method if args.enable else None,
    }

    print(json.dumps(output, indent=2))
    print(f"PR #{args.pull_request}: auto-merge {action_label}", file=sys.stderr)


if __name__ == "__main__":
    main()
