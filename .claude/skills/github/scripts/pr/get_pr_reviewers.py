#!/usr/bin/env python3
"""Get unique reviewers for a GitHub Pull Request.

Enumerates all unique reviewers from review comments, issue comments,
requested reviewers, and submitted reviews. Critical for avoiding
"single-bot blindness" per Skill-PR-001.

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
import warnings
from typing import Any, cast

# Two rungs, both portable. The plugin-root variables win when the host exports
# them; otherwise walk up from this file to the bundled library.
_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
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
    gh_api_paginated,
    gh_graphql,
    resolve_repo_params,
)
from github_core.bot_config import canonicalize_login, is_bot

_PR_AUTHOR_AND_REQUESTS_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      author {
        __typename
        login
        ... on Bot { databaseId }
        ... on User { databaseId }
      }
      reviewRequests(first: 100, after: $cursor) {
        nodes {
          requestedReviewer {
            __typename
            ... on User {
              login
              databaseId
            }
            ... on Team { slug }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}"""

_PR_REVIEWS_QUERY = """\
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviews(first: 100, after: $cursor) {
        nodes {
          author {
            __typename
            login
            ... on Bot { databaseId }
            ... on User { databaseId }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Get unique reviewers for a GitHub PR.",
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--exclude-bots", action="store_true", help="Exclude bot accounts",
    )
    parser.add_argument(
        "--exclude-author", action="store_true", help="Exclude the PR author",
    )
    return parser


def _is_bot(login: str, user_type: str) -> bool:
    """Check if a login belongs to a bot account.

    Delegates to the shared is_bot utility in github_core.bot_config.
    """
    return bool(is_bot(login, user_type))


def _account_id(actor: dict[str, Any]) -> int | None:
    """Return a numeric REST or GraphQL account ID when present."""
    account_id = actor.get("id")
    if not isinstance(account_id, int):
        account_id = actor.get("databaseId")
    return account_id if isinstance(account_id, int) else None


def _actor_login(actor: dict[str, Any], context: str) -> str:
    """Return a string login, rejecting malformed API actor payloads."""
    login = actor.get("login")
    if login is None:
        return ""
    if not isinstance(login, str):
        raise RuntimeError(f"{context} login is not a string")
    return login


def _ensure_reviewer(
    reviewer_map: dict[str, dict[str, Any]],
    login: str,
    user_type: str,
    account_id: int | None = None,
) -> str:
    """Register *login* under its canonical identity and return that key.

    GitHub reports one integration under several logins depending on the API
    path, so keying on the raw login splits a single actor across rows and
    inflates total_reviewers and bot_count. Every observed spelling is kept in
    ``aliases`` and every numeric account ID in ``actor_ids`` so the collapse
    stays auditable. IDs also separate two accounts both reported as
    ``Copilot``.
    """
    canonical: str = canonicalize_login(login, account_id)
    entry = None
    if account_id is not None:
        entry = next(
            (
                candidate
                for candidate in reviewer_map.values()
                if account_id in candidate["actor_ids"]
            ),
            None,
        )
        if entry is not None:
            canonical = entry["login"]
    if entry is None:
        entry = reviewer_map.get(canonical)
    if entry is None:
        entry = reviewer_map[canonical] = {
            "login": canonical,
            "type": user_type,
            "is_bot": _is_bot(canonical, user_type),
            "review_comments": 0,
            "issue_comments": 0,
            "aliases": [],
            "actor_ids": [],
        }
    if login not in entry["aliases"]:
        entry["aliases"].append(login)
    if account_id is not None and account_id not in entry["actor_ids"]:
        entry["actor_ids"].append(account_id)
    return canonical


def _graphql_variables(
    owner: str,
    repo: str,
    pr: int,
    cursor: str | None,
) -> dict[str, str | int]:
    variables: dict[str, str | int] = {
        "owner": owner,
        "repo": repo,
        "number": pr,
    }
    if cursor is not None:
        variables["cursor"] = cursor
    return variables


def _pull_request_data(response: dict[str, Any], pr: int) -> dict[str, Any]:
    repository = response.get("repository")
    pull_request = repository.get("pullRequest") if isinstance(repository, dict) else None
    if not isinstance(pull_request, dict):
        error_and_exit(f"PR #{pr} not found", 2)
    assert isinstance(pull_request, dict)
    return pull_request


def _connection_data(
    pull_request: dict[str, Any],
    field: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return a complete GraphQL connection or reject a partial payload."""
    connection = pull_request.get(field)
    if not isinstance(connection, dict):
        raise RuntimeError(f"GraphQL response missing {field} connection")
    nodes = connection.get("nodes")
    page_info = connection.get("pageInfo")
    if not isinstance(nodes, list):
        raise RuntimeError(f"GraphQL response missing {field}.nodes")
    if not isinstance(page_info, dict):
        raise RuntimeError(f"GraphQL response missing {field}.pageInfo")
    if not isinstance(page_info.get("hasNextPage"), bool):
        raise RuntimeError(f"GraphQL response missing {field}.pageInfo.hasNextPage")
    return nodes, page_info


def _fetch_author_and_review_requests(
    owner: str,
    repo: str,
    pr: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    author: dict[str, Any] = {}
    reviewers: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        response = gh_graphql(
            _PR_AUTHOR_AND_REQUESTS_QUERY,
            _graphql_variables(owner, repo, pr, cursor),
        )
        pull_request = _pull_request_data(response, pr)
        author_payload = pull_request.get("author")
        if author_payload is not None and not isinstance(author_payload, dict):
            raise RuntimeError("PR author payload is not an object")
        if not author and isinstance(author_payload, dict):
            _actor_login(author_payload, "PR author")
            author = author_payload
        nodes, page_info = _connection_data(pull_request, "reviewRequests")
        for node in nodes:
            reviewer = node.get("requestedReviewer") if isinstance(node, dict) else None
            if isinstance(reviewer, dict) and _actor_login(reviewer, "requested reviewer"):
                reviewers.append(reviewer)
        if not page_info.get("hasNextPage"):
            return author, reviewers
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise RuntimeError("Review request pagination reported no end cursor")
        if next_cursor in seen_cursors:
            raise RuntimeError("Review request pagination repeated an end cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _fetch_review_authors(owner: str, repo: str, pr: int) -> list[dict[str, Any]]:
    authors: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        response = gh_graphql(
            _PR_REVIEWS_QUERY,
            _graphql_variables(owner, repo, pr, cursor),
        )
        pull_request = _pull_request_data(response, pr)
        nodes, page_info = _connection_data(pull_request, "reviews")
        for node in nodes:
            author = node.get("author") if isinstance(node, dict) else None
            if isinstance(author, dict) and _actor_login(author, "review author"):
                authors.append(author)
        if not page_info.get("hasNextPage"):
            return authors
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise RuntimeError("Review pagination reported no end cursor")
        if next_cursor in seen_cursors:
            raise RuntimeError("Review pagination repeated an end cursor")
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _fetch_legacy_author(owner: str, repo: str, pr: int) -> str:
    """Return the legacy ``gh pr view --json author`` login."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "author",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Legacy PR author lookup failed: {message}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Legacy PR author response is invalid JSON: {exc}") from exc
    author = payload.get("author")
    if author is None:
        return ""
    if not isinstance(author, dict):
        raise RuntimeError("Legacy PR author payload is not an object")
    return _actor_login(author, "legacy PR author")


def _actor_type(actor: dict[str, Any], field: str) -> str:
    value = actor.get(field, "User")
    return value if isinstance(value, str) else "User"


def _fetch_complete_comments(endpoint: str) -> list[dict[str, Any]]:
    """Reject the helper's documented partial-result warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        try:
            return cast(list[dict[str, Any]], gh_api_paginated(endpoint))
        except UserWarning as exc:
            raise RuntimeError(f"Incomplete pagination for {endpoint}: {exc}") from exc


def _add_comments(
    reviewer_map: dict[str, dict[str, Any]],
    comments: list[dict[str, Any]],
    count_field: str,
) -> None:
    for comment in comments:
        user = comment.get("user")
        if user is None:
            continue
        if not isinstance(user, dict):
            raise RuntimeError("Comment user payload is not an object")
        login = _actor_login(user, "comment author")
        if not login:
            continue
        key = _ensure_reviewer(
            reviewer_map,
            login,
            _actor_type(user, "type"),
            _account_id(user),
        )
        reviewer_map[key][count_field] += 1


def _add_actors(
    reviewer_map: dict[str, dict[str, Any]],
    actors: list[dict[str, Any]],
) -> None:
    for actor in actors:
        login = _actor_login(actor, "reviewer")
        if not login:
            continue
        user_type = _actor_type(actor, "__typename")
        key = _ensure_reviewer(reviewer_map, login, user_type, _account_id(actor))
        reviewer_map[key]["is_bot"] = _is_bot(key, user_type)


def _finalize_reviewers(
    reviewer_map: dict[str, dict[str, Any]],
    exclude_bots: bool,
    exclude_author: bool,
    pr_author: str,
    pr_author_id: int | None,
) -> list[dict[str, Any]]:
    reviewers = list(reviewer_map.values())
    for reviewer in reviewers:
        reviewer["total_comments"] = (
            reviewer["review_comments"] + reviewer["issue_comments"]
        )
    if exclude_bots:
        reviewers = [reviewer for reviewer in reviewers if not reviewer["is_bot"]]
    if exclude_author:
        author_key = canonicalize_login(pr_author, pr_author_id)
        reviewers = [reviewer for reviewer in reviewers if reviewer["login"] != author_key]
    reviewers.sort(key=lambda reviewer: reviewer["total_comments"], reverse=True)
    return reviewers


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    assert_gh_authenticated()
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo
    pr = args.pull_request

    try:
        pr_author_data, requested_reviewers = _fetch_author_and_review_requests(
            owner, repo, pr
        )
        review_authors = _fetch_review_authors(owner, repo, pr)
        legacy_pr_author = _fetch_legacy_author(owner, repo, pr)
        review_comments = _fetch_complete_comments(
            f"repos/{owner}/{repo}/pulls/{pr}/comments"
        )
        issue_comments = _fetch_complete_comments(
            f"repos/{owner}/{repo}/issues/{pr}/comments"
        )
    except RuntimeError as exc:
        error_and_exit(f"Failed to get PR #{pr}: {exc}", 3)

    pr_author_observed = _actor_login(pr_author_data, "PR author")
    pr_author_id = _account_id(pr_author_data)

    reviewer_map: dict[str, dict[str, Any]] = {}

    try:
        _add_comments(reviewer_map, review_comments, "review_comments")
        _add_comments(reviewer_map, issue_comments, "issue_comments")
        _add_actors(reviewer_map, requested_reviewers)
        _add_actors(reviewer_map, review_authors)
        reviewers = _finalize_reviewers(
            reviewer_map,
            args.exclude_bots,
            args.exclude_author,
            pr_author_observed,
            pr_author_id,
        )
    except RuntimeError as exc:
        error_and_exit(f"Failed to get PR #{pr}: {exc}", 3)

    bot_count = sum(1 for r in reviewers if r["is_bot"])
    human_count = len(reviewers) - bot_count

    output = {
        "success": True,
        "pull_request": pr,
        "pr_author": legacy_pr_author,
        "pr_author_id": pr_author_id,
        "pr_author_observed": pr_author_observed or None,
        "pr_author_canonical": (
            canonicalize_login(pr_author_observed, pr_author_id)
            if pr_author_observed
            else None
        ),
        "total_reviewers": len(reviewers),
        "bot_count": bot_count,
        "human_count": human_count,
        "reviewers": reviewers,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
