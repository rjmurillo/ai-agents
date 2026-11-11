"""Shared fixtures for the agent PR intervention tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

OWNER_NAME = "rjmurillo"
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
TRAILER = "Body.\n\n\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)"


def _actor(login: str, typename: str = "User", database_id: int | None = None) -> dict[str, Any]:
    return {"login": login, "__typename": typename, "databaseId": database_id}


BOT = _actor("coderabbitai", "Bot")
HUMAN = _actor("alice")
OWNER = _actor("rjmurillo")


def _thread(first_author: dict[str, Any]) -> dict[str, Any]:
    """A review thread as fetched: only the first comment's author is requested."""
    return {"comments": {"nodes": [{"author": first_author}]}}


def _pr(
    number: int = 1,
    *,
    body: str = TRAILER,
    author: dict[str, Any] | None = None,
    state: str = "MERGED",
    merged: bool = True,
    days_old: float = 5,
    threads: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"PR_{number}",
        "number": number,
        "title": f"PR {number}",
        "url": f"https://github.com/o/r/pull/{number}",
        "state": state,
        "merged": merged,
        "createdAt": (NOW - timedelta(days=days_old)).isoformat(),
        "body": body,
        "author": author or OWNER,
        "reviews": {"nodes": reviews or [], "pageInfo": {"hasNextPage": False}},
        "reviewThreads": {"nodes": threads or [], "pageInfo": {"hasNextPage": False}},
    }


def _page(prs: list[dict[str, Any]], has_next: bool, cursor: str | None = "c1") -> dict[str, Any]:
    return {
        "repository": {
            "pullRequests": {
                "nodes": prs,
                "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
            }
        }
    }
