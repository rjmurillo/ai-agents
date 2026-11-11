#!/usr/bin/env python3
"""Lossless GitHub reads for the reviewer intervention report.

Pages every pull request updated in the window and every review thread on
each, until the API reports no next page (``lossless-queue-reads``). A missing
cursor, a null node, a malformed shape, a page cap, or a nearly empty GraphQL
budget raises ``FetchError`` and names what was not read. This module never
returns a partial set as if it were complete.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

MAX_PR_PAGES = 200
MAX_THREAD_PAGES = 50
PROGRESS_EVERY_PAGES = 10
# GraphQL cost grows with the nested `first` values, not the rows returned. 50 threads
# per pull request cost 858 points over 33 pages on 2026-11-11. A smaller first page
# sends the few busy pull requests to the one-point thread follow-up instead.
PR_PAGE_THREADS = 20
# Stop before this run empties a budget other jobs share.
MIN_REMAINING_POINTS = 100

GraphQL = Callable[[str, dict[str, Any] | None], dict[str, Any]]


class FetchError(RuntimeError):
    """Pagination or response shape prevented a complete read."""


def _parse_updated_at(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise FetchError(f"pull request without an `updatedAt` string: {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FetchError(f"unparseable `updatedAt` {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


_ACTOR = "login __typename"
_THREAD_FIELDS = f"""
  id
  comments(first: 1) {{
    nodes {{ id body createdAt path authorAssociation author {{ {_ACTOR} }} }}
  }}
"""

_PRS_QUERY = f"""
query($owner: String!, $repo: String!, $cursor: String) {{
  rateLimit {{ cost remaining }}
  repository(owner: $owner, name: $repo) {{
    pullRequests(first: 50, orderBy: {{field: UPDATED_AT, direction: DESC}}, after: $cursor) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{
        number
        updatedAt
        body
        authorAssociation
        author {{ {_ACTOR} }}
        reviewThreads(first: {PR_PAGE_THREADS}) {{
          pageInfo {{ hasNextPage endCursor }}
          nodes {{ {_THREAD_FIELDS} }}
        }}
      }}
    }}
  }}
}}"""

_THREADS_QUERY = f"""
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {{
  rateLimit {{ cost remaining }}
  repository(owner: $owner, name: $repo) {{
    pullRequest(number: $number) {{
      reviewThreads(first: 50, after: $cursor) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{ {_THREAD_FIELDS} }}
      }}
    }}
  }}
}}"""


def as_object(value: object, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FetchError(f"malformed GraphQL response: {what} is not an object")
    return value


def _next_cursor(connection: dict[str, Any], what: str) -> str | None:
    info = connection.get("pageInfo")
    if not isinstance(info, dict):
        raise FetchError(f"missing pagination info for {what}")
    if not info.get("hasNextPage"):
        return None
    cursor = info.get("endCursor")
    if not isinstance(cursor, str) or not cursor:
        raise FetchError(f"missing pagination cursor for {what}")
    return cursor


def as_nodes(connection: dict[str, Any], what: str) -> list[dict[str, Any]]:
    nodes = connection.get("nodes")
    if not isinstance(nodes, list):
        raise FetchError(f"missing nodes for {what}")
    if any(n is None for n in nodes):
        raise FetchError(f"null node in {what}; the read is incomplete")
    return [as_object(n, what) for n in nodes]


def normalize_thread(thread: dict[str, Any], pr_number: int) -> dict[str, Any]:
    """Return ``{"id", "opener"}`` for a raw review thread.

    ``opener`` is None for a thread with no comments, else the first comment as
    ``login``, ``kind``, ``association``, ``created_at``, ``body`` and ``path``.
    Callers never read GraphQL field names.
    """
    thread_id = thread.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise FetchError(f"thread on PR #{pr_number} has no id")
    comments = as_object(thread.get("comments"), f"thread {thread_id} comments")
    first = as_nodes(comments, f"thread {thread_id} comments")
    if not first:
        return {"id": thread_id, "opener": None}
    comment = first[0]
    login, kind = actor(comment.get("author"))
    body = comment.get("body")
    return {
        "id": thread_id,
        "opener": {
            "login": login,
            "kind": kind,
            "association": comment.get("authorAssociation"),
            "created_at": comment.get("createdAt"),
            "body": body if isinstance(body, str) else "",
            "path": comment.get("path"),
        },
    }


def actor(raw: object) -> tuple[str, str | None]:
    """Return ``(login, GraphQL type)`` for an author node, ``("", None)`` when absent."""
    if not isinstance(raw, dict):
        return "", None
    login = raw.get("login")
    kind = raw.get("__typename")
    return (login if isinstance(login, str) else ""), (kind if isinstance(kind, str) else None)


def _call(graphql: GraphQL, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Run one query; retry once when the gh call itself times out (the read is idempotent)."""
    try:
        return graphql(query, variables)
    except subprocess.TimeoutExpired:
        logger.warning("gh call timed out; retrying once")
        return graphql(query, variables)


def _account_cost(data: dict[str, Any], counters: dict[str, int], examined: int) -> None:
    """Add this response's GraphQL cost and stop before the shared budget is emptied."""
    limit = data.get("rateLimit")
    if not isinstance(limit, dict) or not isinstance(limit.get("cost"), int):
        logger.warning("response has no rateLimit block; the shared-budget stop is off for it")
        return
    counters["graphql_cost"] += limit["cost"]
    remaining = limit.get("remaining")
    if isinstance(remaining, int) and remaining < MIN_REMAINING_POINTS:
        raise FetchError(
            f"GraphQL budget low ({remaining} points left); stopped after "
            f"{examined} pull requests so the shared budget is not emptied"
        )


def _remaining_threads(
    graphql: GraphQL,
    owner: str,
    repo: str,
    number: int,
    cursor: str,
    counters: dict[str, int],
    examined: int,
) -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    for _ in range(MAX_THREAD_PAGES):
        data = as_object(
            _call(
                graphql,
                _THREADS_QUERY,
                {"owner": owner, "repo": repo, "number": number, "cursor": cursor},
            ),
            "threads page",
        )
        _account_cost(data, counters, examined)
        pr = as_object(
            as_object(data.get("repository"), "repository").get("pullRequest"), "pullRequest"
        )
        conn = as_object(pr.get("reviewThreads"), "reviewThreads")
        threads.extend(as_nodes(conn, f"PR #{number} threads"))
        next_cursor = _next_cursor(conn, f"PR #{number} threads")
        if next_cursor is None:
            return threads
        cursor = next_cursor
    raise FetchError(
        f"thread pagination exceeded {MAX_THREAD_PAGES} pages on PR #{number}; "
        "later threads were not read"
    )


def fetch_pull_requests(
    graphql: GraphQL,
    owner: str,
    repo: str,
    since: datetime,
    stats: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(pull_requests, examined)`` for PRs updated at or after ``since``.

    Each returned PR carries ``number``, ``author_login``, ``author_kind``,
    ``author_association``, ``body`` and a complete list of normalized
    ``threads`` (see ``normalize_thread``). Pull requests arrive ordered by
    ``updatedAt`` descending, so the first one older than ``since`` ends the
    walk: a comment in the window implies its PR was updated in the window. A
    pull request updated during the walk can jump ahead of the cursor and wait
    for the next run. A repeated number is skipped and counted. ``stats``, when
    given, receives ``pages``, ``duplicate_pull_requests_skipped`` and the
    GraphQL ``graphql_cost`` in points.
    """
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    counters = stats if stats is not None else {}
    counters.update({"pages": 0, "duplicate_pull_requests_skipped": 0, "graphql_cost": 0})
    examined = 0
    cursor: str | None = None
    for _ in range(MAX_PR_PAGES):
        variables: dict[str, Any] = {"owner": owner, "repo": repo}
        if cursor:
            variables["cursor"] = cursor
        data = as_object(_call(graphql, _PRS_QUERY, variables), "pull request page")
        counters["pages"] += 1
        _account_cost(data, counters, examined)
        if counters["pages"] % PROGRESS_EVERY_PAGES == 0:
            logger.info("read %d pages, %d pull requests", counters["pages"], examined)
        conn = as_object(
            as_object(data.get("repository"), "repository").get("pullRequests"), "pullRequests"
        )
        reached_boundary = False
        for pr in as_nodes(conn, "pull requests"):
            updated = _parse_updated_at(pr.get("updatedAt"))
            if updated < since:
                reached_boundary = True
                break
            number = pr.get("number")
            if not isinstance(number, int):
                raise FetchError("pull request without a numeric `number`")
            if number in seen:
                counters["duplicate_pull_requests_skipped"] += 1
                continue
            seen.add(number)
            examined += 1
            threads_conn = as_object(pr.get("reviewThreads"), f"PR #{number} reviewThreads")
            threads = as_nodes(threads_conn, f"PR #{number} threads")
            more = _next_cursor(threads_conn, f"PR #{number} threads")
            if more is not None:
                threads.extend(
                    _remaining_threads(graphql, owner, repo, number, more, counters, examined)
                )
            author_login, author_kind = actor(pr.get("author"))
            result.append(
                {
                    "number": number,
                    "author_login": author_login,
                    "author_kind": author_kind,
                    "author_association": pr.get("authorAssociation"),
                    "body": pr["body"] if isinstance(pr.get("body"), str) else "",
                    "threads": [normalize_thread(t, number) for t in threads],
                }
            )
        if reached_boundary:
            return result, examined
        cursor = _next_cursor(conn, "pull requests")
        if cursor is None:
            return result, examined
    raise FetchError(
        f"pull request pagination exceeded {MAX_PR_PAGES} pages; older pull requests were not read"
    )
