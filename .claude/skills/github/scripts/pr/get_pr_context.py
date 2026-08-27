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
from github_core.bot_config import canonicalize_login, is_bot
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_output,
)

JsonObject: TypeAlias = dict[str, Any]
_MAX_REVIEW_THREAD_PAGES = 50

_JSON_FIELDS = (
    "number,title,body,headRefName,headRefOid,baseRefName,baseRefOid,state,author,labels,"
    "reviewRequests,reviews,reviewDecision,commits,additions,deletions,changedFiles,"
    "mergeable,mergeStateStatus,statusCheckRollup,autoMergeRequest,isDraft,"
    "headRepository,headRepositoryOwner,mergedAt,mergedBy,createdAt,updatedAt"
)

_REVIEW_THREADS_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            reviewThreads(first: 100, after: $cursor) {
                totalCount
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                }
            }
        }
    }
}"""


def _review_threads_page(
    owner: str,
    repo: str,
    pr: int,
    cursor: str | None,
) -> JsonObject:
    variables: dict[str, object] = {
        "owner": owner,
        "repo": repo,
        "number": pr,
    }
    if cursor is not None:
        variables["cursor"] = cursor

    try:
        response = gh_graphql(_REVIEW_THREADS_QUERY, variables)
    except (RuntimeError, subprocess.SubprocessError, OSError) as exc:
        error_and_exit(f"Failed to get review threads for PR #{pr}: {exc}", 3)
    if not isinstance(response, dict):
        error_and_exit(
            f"Failed to get review threads for PR #{pr}: response invalid",
            3,
        )

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

    try:
        parsed_pr_data = json.loads(pr_result.stdout)
    except json.JSONDecodeError as exc:
        error_and_exit(f"Failed to get PR #{pr}: invalid JSON: {exc}", 3)
    if not isinstance(parsed_pr_data, dict):
        error_and_exit(f"Failed to get PR #{pr}: response is not an object", 3)
    return cast(JsonObject, parsed_pr_data)


def _review_thread_nodes(review_threads: JsonObject, pr: int) -> list[JsonObject]:
    page_nodes = review_threads.get("nodes")
    if not isinstance(page_nodes, list) or not all(
        isinstance(node, dict)
        and isinstance(node.get("id"), str)
        and isinstance(node.get("isResolved"), bool)
        for node in page_nodes
    ):
        error_and_exit(
            f"Failed to get review threads for PR #{pr}: nodes invalid",
            3,
        )
    return cast(list[JsonObject], page_nodes)


def _review_thread_page_metadata(
    review_threads: JsonObject,
    pr: int,
) -> tuple[int, bool, str | None]:
    page_info = review_threads.get("pageInfo")
    page_total = review_threads.get("totalCount")
    has_next_page = page_info.get("hasNextPage") if isinstance(page_info, dict) else None
    if (
        not isinstance(page_info, dict)
        or not isinstance(has_next_page, bool)
        or type(page_total) is not int
        or page_total < 0
    ):
        error_and_exit(
            f"Failed to get review threads for PR #{pr}: page metadata invalid",
            3,
        )
    assert isinstance(page_info, dict)
    assert isinstance(has_next_page, bool)
    assert type(page_total) is int
    end_cursor = page_info.get("endCursor")
    return page_total, has_next_page, end_cursor if isinstance(end_cursor, str) else None


def _review_thread_counts(
    owner: str,
    repo: str,
    pr: int,
) -> tuple[int, int, int]:
    nodes: list[JsonObject] = []
    cursor: str | None = None
    total_count: int | None = None
    seen_cursors: set[str] = set()
    seen_thread_ids: set[str] = set()

    for _ in range(_MAX_REVIEW_THREAD_PAGES):
        review_threads = _review_threads_page(owner, repo, pr, cursor)
        page_nodes = _review_thread_nodes(review_threads, pr)
        page_total, has_next_page, end_cursor = _review_thread_page_metadata(
            review_threads,
            pr,
        )
        if total_count is not None and page_total != total_count:
            error_and_exit(
                f"Failed to get review threads for PR #{pr}: totalCount changed",
                3,
            )
        total_count = page_total
        page_thread_ids = {cast(str, node["id"]) for node in page_nodes}
        if len(page_thread_ids) != len(page_nodes) or seen_thread_ids.intersection(
            page_thread_ids
        ):
            error_and_exit(
                f"Failed to get review threads for PR #{pr}: duplicate thread",
                3,
            )
        seen_thread_ids.update(page_thread_ids)
        nodes.extend(page_nodes)
        if not has_next_page:
            return total_count, len(nodes), count_unresolved_threads(nodes)
        if not isinstance(end_cursor, str) or not end_cursor:
            error_and_exit(
                f"Failed to get review threads for PR #{pr}: cursor missing",
                3,
            )
        cursor = cast(str, end_cursor)
        if cursor in seen_cursors:
            error_and_exit(
                f"Failed to get review threads for PR #{pr}: cursor repeated",
                3,
            )
        seen_cursors.add(cursor)

    error_and_exit(
        f"Failed to get review threads for PR #{pr}: pagination limit exceeded",
        3,
    )
    raise AssertionError("unreachable")


def _review_counts(reviews_raw: list[object]) -> dict[str, int]:
    review_counts: dict[str, int] = {}
    for rev in reviews_raw:
        state = rev.get("state", "UNKNOWN") if isinstance(rev, dict) else "UNKNOWN"
        review_counts[state] = review_counts.get(state, 0) + 1
    return review_counts


def _valid_status_check(check: JsonObject) -> bool:
    check_type = check.get("__typename")
    if check_type == "CheckRun":
        return (
            isinstance(check.get("name"), str)
            and isinstance(check.get("status"), str)
            and (check.get("conclusion") is None or isinstance(check.get("conclusion"), str))
        )
    if check_type == "StatusContext":
        return isinstance(check.get("context"), str) and isinstance(
            check.get("state"),
            str,
        )
    return False


def _status_checks(pr_data: JsonObject, pr: int) -> list[JsonObject]:
    if "statusCheckRollup" not in pr_data:
        error_and_exit(
            f"Failed to get PR #{pr}: statusCheckRollup missing",
            3,
        )
    status_checks = pr_data["statusCheckRollup"]
    if status_checks is None:
        return []
    if not isinstance(status_checks, list) or not all(
        isinstance(check, dict) and _valid_status_check(check) for check in status_checks
    ):
        error_and_exit(
            f"Failed to get PR #{pr}: statusCheckRollup invalid",
            3,
        )
    return cast(list[JsonObject], status_checks)


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


def _context_fetch_failure_message(
    result: subprocess.CompletedProcess[str],
    command: str,
) -> str:
    message = (result.stderr or result.stdout).strip()
    if message:
        return message
    return f"{command} exited with return code {result.returncode} and no error output"


def _record_context_fetch_failure(
    data: dict[str, object],
    field: str,
    result: subprocess.CompletedProcess[str],
    command: str,
) -> None:
    failures = data.get("context_fetch_failures")
    if not isinstance(failures, list):
        failures = []
        data["context_fetch_failures"] = failures
    failures.append({
        "field": field,
        "message": _context_fetch_failure_message(result, command),
    })


def _author_is_bot(author: object) -> bool | None:
    """Classify the PR author as a bot, or return None when it cannot be read.

    Canonical rule, `scripts/github_core/bot_config.py:328`, verbatim:
    `def is_bot(login: str, user_type: str | None = None) -> bool:`. `canonicalize_login`
    (line 309) runs first so `app/copilot-swe-agent` and `Copilot`, the spellings this repo's
    own bot PRs arrive under, reach it as `[bot]` logins; GitHub's flag feeds `user_type`.

    Stricter/looser/different than canonical. *Stricter input boundary*: canonical takes
    `login: str` and classifies anything, so `"   "` came back a real `False`; this takes
    `author: object` and refuses a non-dict, an empty or non-`str` login, and any login
    bearing whitespace, reclassifying no known bot (no canonical name has any). *Tri-state
    return*: canonical always returns `bool`; this returns `bool | None`, `None` for every
    input that boundary refuses, so a caller fails closed rather than an unearned `False`.
    """
    if not isinstance(author, dict):
        return None
    login = author.get("login")
    if not isinstance(login, str) or not login or any(c.isspace() for c in login):
        return None
    user_type = "Bot" if author.get("is_bot") is True else None
    return bool(is_bot(canonicalize_login(login), user_type))


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
    status_checks = _status_checks(pr_data, pr)
    (
        review_thread_total_count,
        review_thread_returned_count,
        review_thread_unresolved_count,
    ) = _review_thread_counts(owner, repo, pr)
    review_counts = _review_counts(reviews_raw)

    data: dict[str, object] = {
        "number": pr_data.get("number"),
        "title": pr_data.get("title"),
        "body": pr_data.get("body"),
        "state": pr_data.get("state"),
        "is_draft": pr_data.get("isDraft", False),
        "author": author.get("login") if isinstance(author, dict) else None,
        # Three-state; see _author_is_bot. Forwarded as --is-bot (issue #5208).
        "author_is_bot": _author_is_bot(author),
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
        "status_checks": status_checks,
        "status_check_total_count": len(status_checks),
        "review_thread_total_count": review_thread_total_count,
        "review_thread_returned_count": review_thread_returned_count,
        "review_thread_unresolved_count": review_thread_unresolved_count,
        "review_thread_counts_complete": (
            review_thread_returned_count == review_thread_total_count
        ),
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
        "context_fetch_failures": [],
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
        else:
            _record_context_fetch_failure(data, "diff", diff_result, "gh pr diff")

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
        else:
            _record_context_fetch_failure(
                data,
                "files",
                files_result,
                "gh pr diff --name-only",
            )

    write_skill_output(
        data,
        output_format=fmt,
        human_summary=f"PR #{pr}: {pr_data.get('title', '')} ({pr_data.get('state', '')})",
        status="WARNING" if data["context_fetch_failures"] else "PASS",
        script_name="get_pr_context.py",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
