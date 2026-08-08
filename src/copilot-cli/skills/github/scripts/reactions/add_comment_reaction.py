#!/usr/bin/env python3
"""Add a reaction to one or more GitHub comments.

Supports batch operations for improved performance.
Common use: eyes to acknowledge receipt of review comments.

Exit codes follow ADR-035:
    0 - All succeeded
    1 - Invalid parameters / logic error
    3 - Any failed
    4 - Auth error (not authenticated)
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
    gh_graphql,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

REACTION_EMOJI: dict[str, str] = {
    "+1": "\U0001f44d",
    "-1": "\U0001f44e",
    "laugh": "\U0001f604",
    "confused": "\U0001f615",
    "heart": "\u2764\ufe0f",
    "hooray": "\U0001f389",
    "rocket": "\U0001f680",
    "eyes": "\U0001f440",
}

VALID_REACTIONS = list(REACTION_EMOJI.keys())


# Upper bound (seconds) for each gh network call.
GH_TIMEOUT_SECONDS = 30
_MAX_THREAD_PAGES = 50

_REVIEW_THREADS_QUERY = """\
query($owner: String!, $repo: String!, $prNumber: Int!, $cursor: String) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                    comments(first: 1) {
                        nodes {
                            databaseId
                        }
                    }
                }
            }
        }
    }
}"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add a reaction to one or more GitHub comments.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--comment-id",
        nargs="+",
        type=int,
        required=True,
        help="One or more comment IDs to react to",
    )
    parser.add_argument(
        "--comment-type",
        choices=["review", "issue"],
        default="review",
        help='Comment type: "review" for PR review comments, "issue" for issue comments',
    )
    parser.add_argument(
        "--reaction",
        required=True,
        choices=VALID_REACTIONS,
        help="Reaction type",
    )
    parser.add_argument(
        "--pull-request",
        "--expected-pull-request",
        dest="pull_request",
        type=int,
        help="Expected PR number. Review comments from another PR are skipped.",
    )
    add_output_format_arg(parser)
    return parser


def _query_review_comment(
    owner: str,
    repo: str,
    comment_id: int,
) -> dict[str, Any] | None:
    endpoint = f"repos/{owner}/{repo}/pulls/comments/{comment_id}"
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=GH_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip()
        if "HTTP 404" in error or "Not Found" in error:
            return None
        raise RuntimeError(error or f"Failed to query review comment {comment_id}")
    try:
        comment = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON while querying review comment {comment_id}"
        ) from exc
    if not isinstance(comment, dict):
        raise RuntimeError(f"Unexpected review comment payload for {comment_id}")
    return comment


def _pull_request_number(comment: dict[str, Any]) -> int:
    pull_request_url = comment.get("pull_request_url")
    if not isinstance(pull_request_url, str):
        raise RuntimeError("Review comment response omitted pull_request_url")
    try:
        return int(pull_request_url.rstrip("/").rsplit("/", 1)[1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(
            f"Invalid pull_request_url for review comment: {pull_request_url}"
        ) from exc


def _find_review_thread(
    owner: str,
    repo: str,
    pull_request: int,
    root_comment_id: int,
) -> dict[str, Any] | None:
    cursor: str | None = None
    for _page in range(_MAX_THREAD_PAGES):
        variables: dict[str, object] = {
            "owner": owner,
            "repo": repo,
            "prNumber": pull_request,
        }
        if cursor is not None:
            variables["cursor"] = cursor
        data = gh_graphql(_REVIEW_THREADS_QUERY, variables)
        review_threads = _review_threads_page(data, pull_request)
        nodes = review_threads["nodes"]
        thread = _thread_with_root_comment(nodes, root_comment_id)
        if thread is not None:
            return thread
        page_info = review_threads.get("pageInfo")
        if not isinstance(page_info, dict) or not page_info.get("hasNextPage"):
            return None
        cursor_value = page_info.get("endCursor")
        if not isinstance(cursor_value, str) or not cursor_value:
            raise RuntimeError(
                f"Review thread pagination cursor missing for PR #{pull_request}"
            )
        cursor = cursor_value
    raise RuntimeError(
        f"Review thread pagination exceeded {_MAX_THREAD_PAGES} pages"
    )


def _review_threads_page(
    data: dict[str, Any],
    pull_request: int,
) -> dict[str, Any]:
    repository = data.get("repository")
    pull_request_data = (
        repository.get("pullRequest")
        if isinstance(repository, dict)
        else None
    )
    review_threads = (
        pull_request_data.get("reviewThreads")
        if isinstance(pull_request_data, dict)
        else None
    )
    if not isinstance(review_threads, dict):
        raise RuntimeError(f"Review threads unavailable for PR #{pull_request}")
    if not isinstance(review_threads.get("nodes"), list):
        raise RuntimeError(
            f"Review thread nodes unavailable for PR #{pull_request}"
        )
    return review_threads


def _thread_with_root_comment(
    nodes: list[object],
    root_comment_id: int,
) -> dict[str, Any] | None:
    for thread in nodes:
        if not isinstance(thread, dict):
            continue
        comments = thread.get("comments")
        comment_nodes = (
            comments.get("nodes")
            if isinstance(comments, dict)
            else None
        )
        first_comment = (
            comment_nodes[0]
            if isinstance(comment_nodes, list) and comment_nodes
            else None
        )
        if (
            isinstance(first_comment, dict)
            and first_comment.get("databaseId") == root_comment_id
        ):
            return thread
    return None


def query_review_comment_thread_state(
    owner: str,
    repo: str,
    comment_id: int,
    expected_pull_request: int | None = None,
) -> dict[str, Any] | None:
    comment = _query_review_comment(owner, repo, comment_id)
    if comment is None:
        return None
    pull_request = _pull_request_number(comment)
    if (
        expected_pull_request is not None
        and pull_request != expected_pull_request
    ):
        return {
            "pull_request": pull_request,
            "thread_id": None,
            "is_resolved": None,
        }
    in_reply_to_id = comment.get("in_reply_to_id")
    root_comment_id = (
        in_reply_to_id
        if isinstance(in_reply_to_id, int)
        else comment_id
    )
    thread = _find_review_thread(
        owner,
        repo,
        pull_request,
        root_comment_id,
    )
    return {
        "pull_request": pull_request,
        "thread_id": thread.get("id") if thread is not None else None,
        "is_resolved": thread.get("isResolved") if thread is not None else None,
    }


def _review_comment_decision(
    owner: str,
    repo: str,
    comment_id: int,
    expected_pull_request: int | None,
) -> tuple[str, str, dict[str, Any] | None]:
    state = query_review_comment_thread_state(
        owner,
        repo,
        comment_id,
        expected_pull_request,
    )
    if state is None:
        return "SKIP", "comment_not_found", None
    if (
        expected_pull_request is not None
        and state.get("pull_request") != expected_pull_request
    ):
        return "SKIP", "wrong_pull_request", state
    if state.get("thread_id") is None:
        return "SKIP", "thread_not_found", state
    if state.get("is_resolved"):
        return "SKIP", "thread_resolved", state
    return "ACT", "thread_unresolved", state


def _skipped_review_reaction(
    owner: str,
    repo: str,
    comment_id: int,
    pull_request: int | None,
    reaction: str,
    emoji: str,
) -> dict[str, object] | None:
    try:
        action, reason, state = _review_comment_decision(
            owner,
            repo,
            comment_id,
            pull_request,
        )
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        return {
            "action": "SKIP",
            "reason": "thread_state_query_failed",
            "success": False,
            "comment_id": comment_id,
            "error": str(exc),
        }
    if action == "ACT":
        return None
    return {
        "action": action,
        "reason": reason,
        "success": True,
        "comment_id": comment_id,
        "comment_type": "review",
        "thread_id": state.get("thread_id") if state else None,
        "pull_request": state.get("pull_request") if state else None,
        "reaction": reaction,
        "emoji": emoji,
        "error": None,
    }


def _add_reaction(
    endpoint: str,
    comment_id: int,
    comment_type: str,
    reaction: str,
    emoji: str,
) -> dict[str, object]:
    try:
        result = subprocess.run(
            ["gh", "api", endpoint, "-X", "POST", "-f", f"content={reaction}"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "action": "ACT",
            "reason": "reaction_timeout",
            "success": False,
            "comment_id": comment_id,
            "error": f"gh api timed out after {GH_TIMEOUT_SECONDS}s",
        }
    output = result.stderr + result.stdout
    success = result.returncode == 0 or "already reacted" in output
    return {
        "action": "ACT",
        "reason": "reaction_added" if success else "reaction_failed",
        "success": success,
        "comment_id": comment_id,
        "comment_type": comment_type,
        "reaction": reaction,
        "emoji": emoji,
        "error": None if success else result.stderr.strip() or result.stdout.strip(),
    }


def _process_comment(
    owner: str,
    repo: str,
    comment_id: int,
    comment_type: str,
    pull_request: int | None,
    reaction: str,
    emoji: str,
) -> dict[str, object]:
    if comment_type == "review":
        skipped = _skipped_review_reaction(
            owner,
            repo,
            comment_id,
            pull_request,
            reaction,
            emoji,
        )
        if skipped is not None:
            return skipped
        endpoint = f"repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions"
    else:
        endpoint = f"repos/{owner}/{repo}/issues/comments/{comment_id}/reactions"
    return _add_reaction(endpoint, comment_id, comment_type, reaction, emoji)


def _reaction_summary(
    args: argparse.Namespace,
    emoji: str,
    results: list[dict[str, object]],
) -> tuple[dict[str, object], int, int]:
    succeeded = sum(result["reason"] == "reaction_added" for result in results)
    skipped = sum(
        result["action"] == "SKIP" and result["success"]
        for result in results
    )
    failed = sum(not result["success"] for result in results)
    attempted = sum(result["action"] == "ACT" for result in results)
    summary = {
        "action": "ACT" if attempted > 0 else "SKIP",
        "reason": "batch_complete" if failed == 0 else "batch_failed",
        "total_count": len(args.comment_id),
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "reaction": args.reaction,
        "emoji": emoji,
        "comment_type": args.comment_type,
        "results": results,
    }
    return summary, succeeded, skipped


def _write_reaction_result(
    args: argparse.Namespace,
    fmt: str,
    summary: dict[str, object],
    succeeded: int,
    skipped: int,
) -> int:
    failed = int(summary["failed"])
    if failed > 0:
        timeout_failures = sum(
            result["reason"] == "reaction_timeout"
            for result in summary["results"]
        )
        write_skill_error(
            (
                f"Applied '{args.reaction}' to {succeeded}/{len(args.comment_id)} "
                f"comment(s); {failed} failed"
            ),
            3,
            error_type="Timeout" if timeout_failures == failed else "ApiError",
            output_format=fmt,
            script_name="add_comment_reaction.py",
            extra=summary,
        )
        return 3
    write_skill_output(
        summary,
        output_format=fmt,
        human_summary=(
            f"Applied '{args.reaction}' to {succeeded} comment(s); "
            f"skipped {skipped}; {failed} failed"
        ),
        script_name="add_comment_reaction.py",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)
    if args.pull_request is not None and args.pull_request <= 0:
        write_skill_error(
            "Pull request number must be positive.",
            2,
            error_type="InvalidParams",
            output_format=fmt,
            script_name="add_comment_reaction.py",
            extra={"action": "SKIP", "reason": "invalid_pull_request"},
        )
        return 2

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    emoji = REACTION_EMOJI.get(args.reaction, args.reaction)
    results = [
        _process_comment(
            owner,
            repo,
            comment_id,
            args.comment_type,
            args.pull_request,
            args.reaction,
            emoji,
        )
        for comment_id in args.comment_id
    ]
    summary, succeeded, skipped = _reaction_summary(args, emoji, results)
    return _write_reaction_result(
        args,
        fmt,
        summary,
        succeeded,
        skipped,
    )


if __name__ == "__main__":
    raise SystemExit(main())
