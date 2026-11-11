"""Shared builders for the reviewer intervention report tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


BOT = {"login": "rjmurillo-bot", "__typename": "Bot"}


HUMAN = {"login": "rjmurillo", "__typename": "User"}


def stamp(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def make_thread(
    tid: str,
    *,
    author: dict | None = HUMAN,
    body: str = "ADR-042",
    path="a/b.py",
    age=1,
    association: str = "OWNER",
):
    return {
        "id": tid,
        "comments": {
            "nodes": [
                {
                    "id": f"c-{tid}",
                    "body": body,
                    "createdAt": stamp(age),
                    "path": path,
                    "authorAssociation": association,
                    "author": author,
                }
            ]
        },
    }


TRAILER_BODY = (
    "## Summary\n\n\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)"
)


def make_pr(
    number: int,
    threads: list[dict],
    *,
    author: dict | None = BOT,
    body: str = "",
    updated_age: float = 1,
):
    return {
        "number": number,
        "updatedAt": stamp(updated_age),
        "body": body,
        "author": author,
        "reviewThreads": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": threads,
        },
    }


def make_page(prs: list[dict], next_cursor: str | None = None) -> dict:
    return {
        "repository": {
            "pullRequests": {
                "pageInfo": {"hasNextPage": next_cursor is not None, "endCursor": next_cursor},
                "nodes": prs,
            }
        }
    }


class FakeGraphQL:
    """Serve scripted pages. Keyed on the PR cursor or the thread-page request."""

    def __init__(self, pr_pages: dict[str | None, dict], thread_pages: dict | None = None):
        self.pr_pages = pr_pages
        self.thread_pages = thread_pages or {}
        self.calls: list[dict] = []

    def __call__(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        variables = variables or {}
        self.calls.append(variables)
        if "number" in variables:
            return self.thread_pages[(variables["number"], variables["cursor"])]
        return self.pr_pages[variables.get("cursor")]


def three_repeat_pages() -> FakeGraphQL:
    prs = [make_pr(n, [make_thread(f"T{n}")]) for n in (1, 2, 3)]
    return FakeGraphQL({None: make_page(prs)})
