#!/usr/bin/env python3
"""Get context and metadata for a GitHub Pull Request.

Retrieves PR information including:
- Basic metadata (number, title, body, state, author)
- Branch information (head branch, head SHA, base, commits)
- Labels and reviewers
- Optionally includes diff or changed files

Exit codes follow ADR-035:
    0 - Success
    1 - Invalid parameters / logic error
    2 - Not found
    3 - External error (API failure)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, TypeAlias, cast

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
    count_unresolved_threads,
    error_and_exit,
    gh_graphql,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_output,
)

JsonObject: TypeAlias = dict[str, Any]

_JSON_FIELDS = (
    "number,title,body,headRefName,headRefOid,baseRefName,baseRefOid,state,author,labels,"
    "reviewRequests,reviews,reviewDecision,commits,additions,deletions,changedFiles,"
    "mergeable,mergeStateStatus,statusCheckRollup,autoMergeRequest,isDraft,"
    "headRepository,headRepositoryOwner,mergedAt,mergedBy,createdAt,updatedAt"
)

_REVIEW_THREADS_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            reviewThreads(first: 100) {
                totalCount
                nodes {
                    id
                    isResolved
                    isOutdated
                    path
                    line
                    startLine
                    url
                }
            }
        }
    }
}"""


def _review_threads(owner: str, repo: str, pr: int) -> JsonObject:
    try:
        response = cast(
            JsonObject,
            gh_graphql(
                _REVIEW_THREADS_QUERY,
                {"owner": owner, "repo": repo, "number": pr},
            ),
        )
    except RuntimeError as exc:
        error_and_exit(f"Failed to get review threads for PR #{pr}: {exc}", 3)

    repository = response.get("repository")
    if not isinstance(repository, dict):
        error_and_exit(
            f"Failed to get review threads for PR #{pr}: repository missing",
            3,
        )

    pull_request = cast(JsonObject, repository).get("pullRequest")
    if pull_request is None:
        error_and_exit(f"PR #{pr} not found in {owner}/{repo}", 2)
    if not isinstance(pull_request, dict):
        error_and_exit(
            f"Failed to get review threads for PR #{pr}: pullRequest invalid",
            3,
        )

    review_threads = cast(JsonObject, pull_request).get("reviewThreads")
    if not isinstance(review_threads, dict):
        error_and_exit(
            f"Failed to get review threads for PR #{pr}: reviewThreads missing",
            3,
        )
    return cast(JsonObject, review_threads)


def _load_pr_data(repo_flag: str, pr: int) -> JsonObject:
    pr_result = subprocess.run(
        ["gh", "pr", "view", str(pr), "--repo", repo_flag, "--json", _JSON_FIELDS],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if pr_result.returncode != 0:
        err_msg = pr_result.stderr or pr_result.stdout
        if "not found" in err_msg:
            error_and_exit(f"PR #{pr} not found in {repo_flag}", 2)
        error_and_exit(f"Failed to get PR #{pr}: {err_msg}", 3)

    parsed_pr_data = json.loads(pr_result.stdout)
    if not isinstance(parsed_pr_data, dict):
        error_and_exit(f"Failed to get PR #{pr}: response is not an object", 3)
    pr_data = cast(JsonObject, parsed_pr_data)
    if "statusCheckRollup" not in pr_data:
        error_and_exit(
            f"Failed to get PR #{pr}: statusCheckRollup missing from response",
            3,
        )
    return pr_data


def _review_thread_nodes(
    owner: str,
    repo: str,
    pr: int,
) -> tuple[JsonObject, list[JsonObject]]:
    review_threads = _review_threads(owner, repo, pr)
    review_thread_nodes = review_threads.get("nodes")
    if not isinstance(review_thread_nodes, list):
        error_and_exit(
            f"Failed to get review threads for PR #{pr}: reviewThreads.nodes missing",
            3,
        )
    return review_threads, cast(list[JsonObject], review_thread_nodes)


def _review_counts(reviews_raw: list[object]) -> dict[str, int]:
    review_counts: dict[str, int] = {}
    for rev in reviews_raw:
        state = rev.get("state", "UNKNOWN") if isinstance(rev, dict) else "UNKNOWN"
        review_counts[state] = review_counts.get(state, 0) + 1
    return review_counts


def _check_context_total_count(status_check_rollup: object) -> int | None:
    check_contexts = (
        status_check_rollup.get("contexts")
        if isinstance(status_check_rollup, dict)
        else None
    )
    return check_contexts.get("totalCount") if isinstance(check_contexts, dict) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get context and metadata for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request",
        type=int,
        required=True,
        help="Pull request number",
    )
    parser.add_argument(
        "--include-diff",
        action="store_true",
        help="Include the PR diff (may be large)",
    )
    parser.add_argument(
        "--include-changed-files",
        action="store_true",
        help="Include list of changed files",
    )
    parser.add_argument(
        "--diff-stat",
        action="store_true",
        help="With --include-diff, return stat format instead of full diff",
    )
    add_output_format_arg(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request
    repo_flag = f"{owner}/{repo}"
    fmt = get_output_format(args.output_format)

    pr_data = _load_pr_data(repo_flag, pr)
    labels = [label.get("name", "") for label in pr_data.get("labels", [])]
    author = pr_data.get("author")
    merged_by = pr_data.get("mergedBy")
    head_repo = pr_data.get("headRepository") or {}
    head_repo_owner = pr_data.get("headRepositoryOwner") or (head_repo.get("owner") or {})
    auto_merge = pr_data.get("autoMergeRequest")
    reviews_raw = pr_data.get("reviews") or []
    status_check_rollup = pr_data.get("statusCheckRollup")
    review_threads, review_thread_nodes = _review_thread_nodes(owner, repo, pr)
    review_counts = _review_counts(reviews_raw)

    data: dict[str, object] = {
        "number": pr_data.get("number"),
        "title": pr_data.get("title"),
        "body": pr_data.get("body"),
        "state": pr_data.get("state"),
        "is_draft": pr_data.get("isDraft", False),
        "author": author.get("login") if isinstance(author, dict) else None,
        "head_branch": pr_data.get("headRefName"),
        "head_sha": pr_data.get("headRefOid"),
        "head_repo": head_repo.get("nameWithOwner"),
        "head_repo_name": head_repo.get("name"),
        "head_repo_owner": head_repo_owner.get("login"),
        "base_branch": pr_data.get("baseRefName"),
        "base_sha": pr_data.get("baseRefOid"),
        "labels": labels,
        "commits": len(pr_data.get("commits", [])),
        "additions": pr_data.get("additions"),
        "deletions": pr_data.get("deletions"),
        "changed_files": pr_data.get("changedFiles"),
        "mergeable": pr_data.get("mergeable"),
        "merge_state_status": pr_data.get("mergeStateStatus"),
        "status_check_rollup": status_check_rollup,
        "status_check_state": (
            status_check_rollup.get("state")
            if isinstance(status_check_rollup, dict)
            else None
        ),
        "status_check_context_total_count": _check_context_total_count(
            status_check_rollup
        ),
        "review_threads": review_thread_nodes,
        "review_thread_total_count": review_threads.get("totalCount"),
        "unresolved_review_threads": count_unresolved_threads(review_thread_nodes),
        "auto_merge": auto_merge is not None,
        "auto_merge_method": (
            auto_merge.get("mergeMethod") if isinstance(auto_merge, dict) else None
        ),
        "reviews": reviews_raw,
        "review_decision": pr_data.get("reviewDecision"),
        "review_counts": review_counts,
        "merged": bool(pr_data.get("mergedAt")),
        "merged_by": merged_by.get("login") if merged_by else None,
        "created_at": pr_data.get("createdAt"),
        "updated_at": pr_data.get("updatedAt"),
        "diff": None,
        "files": None,
        "owner": owner,
        "repo": repo,
    }

    if args.include_diff:
        diff_args = ["gh", "pr", "diff", str(pr), "--repo", repo_flag]
        if args.diff_stat:
            diff_args.append("--stat")
        diff_result = subprocess.run(
            diff_args,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if diff_result.returncode == 0:
            data["diff"] = diff_result.stdout

    if args.include_changed_files:
        files_result = subprocess.run(
            ["gh", "pr", "diff", str(pr), "--repo", repo_flag, "--name-only"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if files_result.returncode == 0:
            data["files"] = [f for f in files_result.stdout.splitlines() if f.strip()]

    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"PR #{pr}: {pr_data.get('title', '')} ({pr_data.get('state', '')})",
        status="PASS",
        script_name="get_pr_context.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
