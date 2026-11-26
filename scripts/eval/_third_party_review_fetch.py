"""Lossless GitHub reads for the third-party review mining run.

Reads the newest N pull requests by creation order, with every review thread,
every comment in each thread, every review, and every top-level comment. Each
connection is paged until the API reports no next page
(``lossless-queue-reads``). A missing cursor, a null node, a page cap, or a
nearly empty GraphQL budget raises ``FetchError`` and names what was not read.
A partial set is never returned as complete.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from typing import Any

from scripts.graphql_connection import FetchError, as_nodes, as_object, next_cursor

logger = logging.getLogger(__name__)

GraphQL = Callable[[str, dict[str, Any] | None], dict[str, Any]]

PR_PAGE_SIZE = 20
MAX_PR_PAGES = 200
MAX_SUB_PAGES = 50
MIN_REMAINING_POINTS = 200
# First-page sizes. A busier connection falls through to a follow-up query.
FIRST_THREADS = 40
FIRST_THREAD_COMMENTS = 8
FIRST_REVIEWS = 20
FIRST_COMMENTS = 20

_ACTOR = "author { login __typename }"
_COMMENT = f"id {_ACTOR} body createdAt url originalCommit {{ oid }} commit {{ oid }}"
_THREAD = (
    "id isResolved isOutdated path line originalLine startLine originalStartLine "
    "resolvedBy { login } "
    f"comments(first: {FIRST_THREAD_COMMENTS}) {{ pageInfo {{ hasNextPage endCursor }} "
    f"nodes {{ {_COMMENT} }} }}"
)
_REVIEW = f"id {_ACTOR} state body submittedAt commit {{ oid }}"
_ISSUE_COMMENT = f"id {_ACTOR} body createdAt"

_PR_FIELDS = f"""
  number title state createdAt mergedAt closedAt body
  {_ACTOR}
  baseRefName baseRefOid headRefName headRefOid
  mergeCommit {{ oid }}
  additions deletions changedFiles
  reviewThreads(first: {FIRST_THREADS}) {{
    pageInfo {{ hasNextPage endCursor }} nodes {{ {_THREAD} }}
  }}
  reviews(first: {FIRST_REVIEWS}) {{
    pageInfo {{ hasNextPage endCursor }} nodes {{ {_REVIEW} }}
  }}
  comments(first: {FIRST_COMMENTS}) {{
    pageInfo {{ hasNextPage endCursor }} nodes {{ {_ISSUE_COMMENT} }}
  }}
"""

_PRS_QUERY = f"""
query($owner: String!, $repo: String!, $cursor: String, $size: Int!) {{
  rateLimit {{ cost remaining }}
  repository(owner: $owner, name: $repo) {{
    pullRequests(first: $size, orderBy: {{field: CREATED_AT, direction: DESC}}, after: $cursor) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{ {_PR_FIELDS} }}
    }}
  }}
}}"""

_PR_CONNECTION_QUERY = """
query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  rateLimit { cost remaining }
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      %s(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor } nodes { %s }
      }
    }
  }
}"""

_THREAD_COMMENTS_QUERY = f"""
query($id: ID!, $cursor: String) {{
  rateLimit {{ cost remaining }}
  node(id: $id) {{
    ... on PullRequestReviewThread {{
      comments(first: 50, after: $cursor) {{
        pageInfo {{ hasNextPage endCursor }} nodes {{ {_COMMENT} }}
      }}
    }}
  }}
}}"""

_CONNECTION_NODES = {
    "reviewThreads": _THREAD,
    "reviews": _REVIEW,
    "comments": _ISSUE_COMMENT,
}


class Budget:
    """Tracks GraphQL cost and refuses a request when the shared budget is low."""

    def __init__(self, floor: int = MIN_REMAINING_POINTS) -> None:
        self._floor = floor
        self._cost = 0
        self._remaining: int | None = None
        self._requests = 0

    @property
    def cost(self) -> int:
        """Points spent by every request this budget accounted."""
        return self._cost

    @property
    def requests(self) -> int:
        """Requests this budget accounted."""
        return self._requests

    def account(self, data: dict[str, Any]) -> None:
        self._requests += 1
        limit = data.get("rateLimit")
        if isinstance(limit, dict) and isinstance(limit.get("cost"), int):
            self._cost += limit["cost"]
            if isinstance(limit.get("remaining"), int):
                self._remaining = limit["remaining"]

    def require(self, what: str) -> None:
        if self._remaining is not None and self._remaining < self._floor:
            raise FetchError(
                f"GraphQL budget low ({self._remaining} points left) before {what}; "
                "stopped so the shared budget is not emptied"
            )


def _call(graphql: GraphQL, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    try:
        return as_object(graphql(query, variables), "response")
    except subprocess.TimeoutExpired:
        logger.warning("gh call timed out; retrying once")
        return as_object(graphql(query, variables), "response")


def _drain_pr_connection(
    graphql: GraphQL,
    owner: str,
    repo: str,
    number: int,
    field: str,
    cursor: str,
    budget: Budget,
) -> list[dict[str, Any]]:
    query = _PR_CONNECTION_QUERY % (field, _CONNECTION_NODES[field])
    out: list[dict[str, Any]] = []
    for _ in range(MAX_SUB_PAGES):
        budget.require(f"PR #{number} {field}")
        data = _call(
            graphql, query, {"owner": owner, "repo": repo, "number": number, "cursor": cursor}
        )
        budget.account(data)
        pr = as_object(as_object(data.get("repository"), "repository").get("pullRequest"), "pr")
        conn = as_object(pr.get(field), f"PR #{number} {field}")
        out.extend(as_nodes(conn, f"PR #{number} {field}"))
        nxt = next_cursor(conn, f"PR #{number} {field}")
        if nxt is None:
            return out
        cursor = nxt
    raise FetchError(f"PR #{number} {field} exceeded {MAX_SUB_PAGES} pages; later rows unread")


def _drain_thread_comments(
    graphql: GraphQL, thread_id: str, cursor: str, budget: Budget
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(MAX_SUB_PAGES):
        budget.require(f"thread {thread_id} comments")
        data = _call(graphql, _THREAD_COMMENTS_QUERY, {"id": thread_id, "cursor": cursor})
        budget.account(data)
        conn = as_object(as_object(data.get("node"), "thread").get("comments"), "comments")
        out.extend(as_nodes(conn, f"thread {thread_id} comments"))
        nxt = next_cursor(conn, f"thread {thread_id} comments")
        if nxt is None:
            return out
        cursor = nxt
    raise FetchError(f"thread {thread_id} comments exceeded {MAX_SUB_PAGES} pages")


def complete_pr(
    graphql: GraphQL, owner: str, repo: str, pr: dict[str, Any], budget: Budget
) -> dict[str, Any]:
    """Return ``pr`` with every connection fully paged, as plain node lists."""
    number = pr.get("number")
    if not isinstance(number, int):
        raise FetchError("pull request without a numeric `number`")
    done = dict(pr)
    for field in ("reviewThreads", "reviews", "comments"):
        conn = as_object(pr.get(field), f"PR #{number} {field}")
        nodes = as_nodes(conn, f"PR #{number} {field}")
        more = next_cursor(conn, f"PR #{number} {field}")
        if more is not None:
            nodes.extend(_drain_pr_connection(graphql, owner, repo, number, field, more, budget))
        done[field] = nodes
    threads = []
    for thread in done["reviewThreads"]:
        conn = as_object(thread.get("comments"), f"PR #{number} thread comments")
        comments = as_nodes(conn, f"PR #{number} thread comments")
        more = next_cursor(conn, f"PR #{number} thread comments")
        if more is not None:
            comments.extend(_drain_thread_comments(graphql, str(thread.get("id")), more, budget))
        threads.append({**thread, "comments": comments})
    done["reviewThreads"] = threads
    return done


def fetch_recent_pull_requests(
    graphql: GraphQL, owner: str, repo: str, limit: int, budget: Budget | None = None
) -> list[dict[str, Any]]:
    """The ``limit`` newest pull requests by creation, every connection complete."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    budget = budget or Budget()
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    cursor: str | None = None
    for page in range(MAX_PR_PAGES):
        budget.require(f"pull request page {page + 1}")
        size = min(PR_PAGE_SIZE, limit - len(out))
        variables: dict[str, Any] = {"owner": owner, "repo": repo, "size": size}
        if cursor:
            variables["cursor"] = cursor
        data = _call(graphql, _PRS_QUERY, variables)
        budget.account(data)
        conn = as_object(
            as_object(data.get("repository"), "repository").get("pullRequests"), "pullRequests"
        )
        for pr in as_nodes(conn, "pull requests"):
            number = pr.get("number")
            if not isinstance(number, int):
                raise FetchError("pull request without a numeric `number`")
            if number in seen:
                continue
            seen.add(number)
            out.append(complete_pr(graphql, owner, repo, pr, budget))
            if len(out) >= limit:
                return out
        logger.info("read %d pull requests, %d points spent", len(out), budget.cost)
        cursor = next_cursor(conn, "pull requests")
        if cursor is None:
            return out
    raise FetchError(f"pull request pagination exceeded {MAX_PR_PAGES} pages")
