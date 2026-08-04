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

from github_core.api import (  # noqa: E402
    assert_gh_authenticated,
    error_and_exit,
    gh_api_paginated,
    gh_graphql,
    resolve_repo_params,
)
from github_core.bot_config import canonicalize_login, is_bot  # noqa: E402

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


def _fetch_author_and_review_requests(
    owner: str,
    repo: str,
    pr: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    author: dict[str, Any] = {}
    reviewers: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        response = gh_graphql(
            _PR_AUTHOR_AND_REQUESTS_QUERY,
            _graphql_variables(owner, repo, pr, cursor),
        )
        pull_request = _pull_request_data(response, pr)
        if not author and isinstance(pull_request.get("author"), dict):
            author = pull_request["author"]
        connection = pull_request.get("reviewRequests") or {}
        for node in connection.get("nodes") or []:
            reviewer = node.get("requestedReviewer") if isinstance(node, dict) else None
            if isinstance(reviewer, dict) and reviewer.get("login"):
                reviewers.append(reviewer)
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return author, reviewers
        cursor = page_info.get("endCursor")
        if not isinstance(cursor, str) or not cursor:
            raise RuntimeError("Review request pagination reported no end cursor")


def _fetch_review_authors(owner: str, repo: str, pr: int) -> list[dict[str, Any]]:
    authors: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        response = gh_graphql(
            _PR_REVIEWS_QUERY,
            _graphql_variables(owner, repo, pr, cursor),
        )
        pull_request = _pull_request_data(response, pr)
        connection = pull_request.get("reviews") or {}
        for node in connection.get("nodes") or []:
            author = node.get("author") if isinstance(node, dict) else None
            if isinstance(author, dict) and author.get("login"):
                authors.append(author)
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return authors
        cursor = page_info.get("endCursor")
        if not isinstance(cursor, str) or not cursor:
            raise RuntimeError("Review pagination reported no end cursor")


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
    except RuntimeError as exc:
        error_and_exit(f"Failed to get PR #{pr}: {exc}", 3)

    raw_pr_author = pr_author_data.get("login", "")
    pr_author = raw_pr_author if isinstance(raw_pr_author, str) else ""
    pr_author_id = _account_id(pr_author_data)

    reviewer_map: dict[str, dict[str, Any]] = {}

    review_comments = gh_api_paginated(f"repos/{owner}/{repo}/pulls/{pr}/comments")
    for c in review_comments:
        user = c.get("user") or {}
        login = user.get("login", "")
        if not login:
            continue
        user_type = user.get("type", "User")
        key = _ensure_reviewer(reviewer_map, login, user_type, _account_id(user))
        reviewer_map[key]["review_comments"] += 1

    issue_comments = gh_api_paginated(f"repos/{owner}/{repo}/issues/{pr}/comments")
    for c in issue_comments:
        user = c.get("user") or {}
        login = user.get("login", "")
        if not login:
            continue
        user_type = user.get("type", "User")
        key = _ensure_reviewer(reviewer_map, login, user_type, _account_id(user))
        reviewer_map[key]["issue_comments"] += 1

    for r in requested_reviewers:
        login = r.get("login", "")
        if login:
            user_type = r.get("__typename", "User")
            _ensure_reviewer(reviewer_map, login, user_type, _account_id(r))

    for author in review_authors:
        login = author.get("login", "")
        if login:
            user_type = author.get("__typename", "User")
            key = _ensure_reviewer(reviewer_map, login, user_type, _account_id(author))
            reviewer_map[key]["is_bot"] = _is_bot(key, user_type)

    reviewers = list(reviewer_map.values())
    for r in reviewers:
        r["total_comments"] = r["review_comments"] + r["issue_comments"]

    if args.exclude_bots:
        reviewers = [r for r in reviewers if not r["is_bot"]]
    if args.exclude_author:
        # Compare canonical identities: an author who also reviews under an
        # alias would otherwise survive the filter as a separate actor.
        author_key = canonicalize_login(pr_author, pr_author_id)
        reviewers = [r for r in reviewers if r["login"] != author_key]

    reviewers.sort(key=lambda r: r["total_comments"], reverse=True)

    bot_count = sum(1 for r in reviewers if r["is_bot"])
    human_count = len(reviewers) - bot_count

    output = {
        "success": True,
        "pull_request": pr,
        "pr_author": pr_author,
        "pr_author_id": pr_author_id,
        "total_reviewers": len(reviewers),
        "bot_count": bot_count,
        "human_count": human_count,
        "reviewers": reviewers,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
