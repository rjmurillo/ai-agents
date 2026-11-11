"""Strict review-thread pager: read every page or raise.

``get_unresolved_review_threads`` in ``review_threads.py`` warns and returns a
partial list when a page fails. A caller that acts on "no unresolved threads"
cannot accept that, so this pager raises instead
(``lossless-queue-reads.md``, issue #7222).
"""

from __future__ import annotations

from collections.abc import Callable

# Safety bound on the loop. A PR with more than 5000 threads is a misuse, so the
# pager raises rather than spin.
REVIEW_THREADS_MAX_PAGES = 50


class ReviewThreadsIncompleteError(RuntimeError):
    """Raised when a review-thread read cannot reach the last page.

    The read stopped on a missing connection, missing page metadata, a missing
    cursor, or the page cap. The message states how many threads were read, so a caller reports
    an incomplete read and never presents it as the full set
    (``lossless-queue-reads.md``).
    """


def collect_all_review_threads(
    fetch_page: Callable[[str | None], dict],
    pull_request: int,
    *,
    max_pages: int = REVIEW_THREADS_MAX_PAGES,
) -> list[dict]:
    """Read every reviewThreads node on a PR, or raise.

    ``fetch_page(cursor)`` runs one GraphQL page and returns its ``data``
    dict. The caller owns the query, so each script keeps the node fields it
    needs. Unlike ``get_unresolved_review_threads``, which warns and returns
    what it has, this raises ``ReviewThreadsIncompleteError`` for a missing
    ``reviewThreads`` connection, a missing or non-boolean ``pageInfo.hasNextPage``
    (the last page cannot be proven), ``hasNextPage`` with no ``endCursor``, and
    more than ``max_pages`` pages. A transport failure raised by
    ``fetch_page`` (``RuntimeError``) propagates unchanged.

    Returns:
        All thread nodes, resolved and unresolved, in page order.
    """
    nodes: list[dict] = []
    cursor: str | None = None
    for page in range(1, max_pages + 1):
        data = fetch_page(cursor)
        pull_request_obj = (data.get("repository") or {}).get("pullRequest") or {}
        connection = pull_request_obj.get("reviewThreads")
        if connection is None or connection.get("nodes") is None:
            raise ReviewThreadsIncompleteError(
                f"reviewThreads missing from response for PR #{pull_request} "
                f"on page {page}; read {len(nodes)} thread(s) before it stopped"
            )
        nodes.extend(connection["nodes"])
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict) or not isinstance(page_info.get("hasNextPage"), bool):
            raise ReviewThreadsIncompleteError(
                f"pageInfo.hasNextPage missing or not a boolean for PR #{pull_request} "
                f"on page {page}; read {len(nodes)} thread(s) before it stopped"
            )
        if not page_info["hasNextPage"]:
            return nodes
        cursor = page_info.get("endCursor")
        if not cursor:
            raise ReviewThreadsIncompleteError(
                f"hasNextPage=true but endCursor empty for PR #{pull_request} "
                f"on page {page}; read {len(nodes)} thread(s) before it stopped"
            )
    raise ReviewThreadsIncompleteError(
        f"review thread pagination on PR #{pull_request} exceeded {max_pages} pages; "
        f"read {len(nodes)} thread(s) before it stopped"
    )
