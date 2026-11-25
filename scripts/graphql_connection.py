"""Strict readers for one GraphQL connection page.

Shared by the lossless fetchers ``scripts/reviewer_intervention_fetch.py`` and
``scripts/eval/_third_party_review_fetch.py``. Each reader raises
``FetchError`` when the page cannot prove a complete read
(``lossless-queue-reads``): missing nodes, a null node, a non-object node,
missing page metadata, or a next page with no cursor.
"""

from __future__ import annotations

from typing import Any


class FetchError(RuntimeError):
    """Pagination or response shape prevented a complete read."""


def as_object(value: object, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FetchError(f"malformed GraphQL response: {what} is not an object")
    return value


def as_nodes(connection: dict[str, Any], what: str) -> list[dict[str, Any]]:
    nodes = connection.get("nodes")
    if not isinstance(nodes, list):
        raise FetchError(f"missing nodes for {what}")
    if any(n is None for n in nodes):
        raise FetchError(f"null node in {what}; the read is incomplete")
    return [as_object(n, what) for n in nodes]


def next_cursor(connection: dict[str, Any], what: str) -> str | None:
    info = connection.get("pageInfo")
    if not isinstance(info, dict):
        raise FetchError(f"missing pagination info for {what}")
    has_next = info.get("hasNextPage")
    if not isinstance(has_next, bool):
        raise FetchError(f"missing pagination flag for {what}")
    if not has_next:
        return None
    cursor = info.get("endCursor")
    if not isinstance(cursor, str) or not cursor:
        raise FetchError(f"missing pagination cursor for {what}")
    return cursor
