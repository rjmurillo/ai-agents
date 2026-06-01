"""Canonical: scripts/github_core/review_threads.py. Sync via scripts/sync_plugin_lib.py.

Extracted from ``scripts/github_core/api.py`` (Issue #1910) as a cohesive
module. ``api.py`` re-exports every public and private name defined here so
existing ``from .api import ...`` call sites stay valid.
"""

from __future__ import annotations

import enum
import logging
import time
import warnings

from .log_safety import safe_log_str

logger = logging.getLogger(__name__)


def _thread_is_unresolved(thread: dict) -> bool:
    """Return True only when a thread is explicitly not resolved.

    A missing ``isResolved`` key defaults to resolved (True), and an explicit
    ``null`` (``None``) from the GraphQL payload is treated the same way, so a
    malformed or absent value never silently counts as unresolved.
    """
    resolved = thread.get("isResolved", True)
    if resolved is None:
        resolved = True
    return not resolved


def count_unresolved_threads(thread_nodes: list[dict]) -> int:
    """Count threads whose ``isResolved`` is False.

    Single authoritative definition of "unresolved" (DRY): the merge-ready
    inline-page filter and the paginated-helper post-filter MUST share this
    rule via ``_thread_is_unresolved``. If the rule changes (e.g., treating an
    outdated thread differently), one edit propagates everywhere. A missing or
    ``null`` ``isResolved`` defaults to resolved so a malformed thread does not
    silently count as unresolved.
    """
    return sum(1 for t in thread_nodes if _thread_is_unresolved(t))


def filter_unresolved_threads(thread_nodes: list[dict]) -> list[dict]:
    """Return only threads whose ``isResolved`` is False. See
    ``count_unresolved_threads`` for the canonical definition.
    """
    return [t for t in thread_nodes if _thread_is_unresolved(t)]


def transform_review_thread(thread: dict, include_comments: bool = False) -> dict:
    """Transform a raw GraphQL review-thread node into the canonical flat shape.

    Single authoritative definition (DRY) of the review-thread output shape
    shared by ``get_pr_review_threads.py`` and
    ``get_unresolved_review_threads.py``. A consumer that reads one script's
    ``threads`` list can read the other's without a shape branch, which is the
    bug this consolidates: the lighter unresolved script previously emitted raw
    GraphQL nodes (``{"id", "isResolved", "comments": {"nodes": [...]}}``) while
    the richer script emitted this flat shape, so ``thread["comments"][-1]``
    crashed against one and worked against the other.

    ``include_comments`` controls whether the full comment list is materialized.
    When False (the cheap-probe default), ``comments`` is None and only the
    ``first_comment_*`` fields are populated; the caller still pays for one
    comment per thread in its GraphQL query, never the whole conversation.
    """
    comments_data = thread.get("comments") or {}
    comments_nodes = comments_data.get("nodes") or []
    first = comments_nodes[0] if comments_nodes else None

    result: dict = {
        "thread_id": thread.get("id"),
        "is_resolved": thread.get("isResolved") is True,
        "is_outdated": thread.get("isOutdated") is True,
        "path": thread.get("path"),
        "line": thread.get("line"),
        "start_line": thread.get("startLine"),
        "diff_side": thread.get("diffSide"),
        "comment_count": comments_data.get("totalCount") or 0,
        "first_comment_id": first.get("databaseId") if first else None,
        "first_comment_author": (
            first.get("author", {}).get("login") if first and first.get("author") else None
        ),
        "first_comment_body": first.get("body") if first else None,
        "first_comment_created_at": first.get("createdAt") if first else None,
        "comments": None,
    }

    if include_comments:
        result["comments"] = [
            {
                "id": c.get("databaseId"),
                "author": c.get("author", {}).get("login") if c.get("author") else None,
                "body": c.get("body"),
                "created_at": c.get("createdAt"),
            }
            for c in comments_nodes
        ]

    return result


# Safety bound on the reviewThreads pagination loop. A PR with >5000 threads
# is almost certainly a misuse rather than a real review state; we exit
# rather than spin forever. The PR #1887 retrospective records that the
# prior single-page first:100 query masked 6+ unresolved threads twice.
_REVIEW_THREADS_MAX_PAGES = 50

_REVIEW_THREADS_QUERY = """\
query($owner: String!, $name: String!, $prNumber: Int!, $cursor: String) {
    repository(owner: $owner, name: $name) {
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


class FetchStatus(enum.StrEnum):
    """Result classification for one reviewThreads page fetch.

    The caller distinguishes ``TRANSPORT_ERROR`` (return [] to preserve the
    never-raises contract) from ``STRUCTURAL_MISSING`` (break the loop with
    whatever was collected). ``OK`` means a usable page is returned.
    Using StrEnum instead of bare strings keeps the type checker honest
    and makes a typo (``FetchStatus.OK_`` vs ``FetchStatus.OK``) a fail-
    fast attribute error rather than a silent miss.
    """

    OK = "ok"
    TRANSPORT_ERROR = "transport_error"
    STRUCTURAL_MISSING = "structural_missing"


def _log_structural_missing(
    owner: str, repo: str, pull_request: int,
    pages_seen: int, aggregated_count: int, reason: str,
) -> None:
    """Emit the structured ``op=review_threads_failed`` line for a structural
    problem in the GraphQL response. Centralizes the greppable failure reasons,
    which currently include ``pr_not_found``, ``field_missing``,
    ``nodes_missing``, ``structural_failure``, and ``cursor_missing``. Not every
    reason denotes a strictly missing field; ``structural_failure`` covers a
    malformed-but-present structure.
    """
    logger.warning(
        "op=review_threads_failed pr=%d owner=%s repo=%s "
        "page=%d aggregated=%d reason=%s",
        pull_request, owner, repo, pages_seen, aggregated_count, reason,
    )


def _unwrap_review_threads(
    data: dict,
    owner: str,
    repo: str,
    pull_request: int,
    pages_seen: int,
    aggregated_count: int,
) -> dict | None:
    """Pull the reviewThreads connection out of a GraphQL response.

    Returns the reviewThreads dict, or None on a structural-missing shape
    (logging a distinct ``reason=...``). The three reasons mirror the taxonomy
    in .claude/skills/github/scripts/pr/get_pr_review_threads.py: pr_not_found,
    field_missing, and nodes_missing (the connection is present but its node
    list is null).
    """
    repository = data.get("repository") or {}
    pull_request_obj = repository.get("pullRequest")
    if pull_request_obj is None:
        reason = "pr_not_found"
    else:
        review_threads: dict | None = pull_request_obj.get("reviewThreads")
        if review_threads is None:
            reason = "field_missing"
        elif review_threads.get("nodes") is None:
            reason = "nodes_missing"
        else:
            return review_threads

    _log_structural_missing(
        owner, repo, pull_request, pages_seen, aggregated_count, reason,
    )
    return None


def _fetch_review_threads_page(
    owner: str,
    repo: str,
    pull_request: int,
    cursor: str | None,
    pages_seen: int,
    aggregated_count: int,
) -> tuple[FetchStatus, dict | None]:
    """Fetch one page of reviewThreads.

    Returns ``(status, review_threads_dict)``. status is one of
    ``FetchStatus.OK`` / ``FetchStatus.TRANSPORT_ERROR`` / ``FetchStatus.STRUCTURAL_MISSING``.
    Each failure branch logs a distinct ``op=review_threads_failed
    reason=...`` line so the surface is greppable.
    """
    # Lazy import avoids a github_core.api <-> review_threads import cycle,
    # matching the existing convention in github_core/validation.py.
    from .api import gh_graphql

    variables: dict = {"owner": owner, "name": repo, "prNumber": pull_request}
    if cursor is not None:
        variables["cursor"] = cursor

    try:
        data = gh_graphql(_REVIEW_THREADS_QUERY, variables)
    except RuntimeError as exc:
        logger.warning(
            "op=review_threads_failed pr=%d owner=%s repo=%s "
            "page=%d aggregated=%d reason=graphql_error error=%s",
            pull_request, owner, repo, pages_seen, aggregated_count,
            safe_log_str(exc),
        )
        warnings.warn(
            f"Failed to query review threads for PR #{pull_request} "
            f"on page {pages_seen} (collected {aggregated_count} so far): {exc}",
            stacklevel=2,
        )
        return FetchStatus.TRANSPORT_ERROR, None

    review_threads = _unwrap_review_threads(
        data, owner, repo, pull_request, pages_seen, aggregated_count,
    )
    if review_threads is None:
        return FetchStatus.STRUCTURAL_MISSING, None
    return FetchStatus.OK, review_threads


def _log_review_threads_page(
    pull_request: int, pages_seen: int, cursor: str | None,
    page_info: dict, page_nodes: list, aggregated_count: int,
) -> None:
    """Per-page DEBUG log; full cursor so adjacent pages with shared 8-char
    prefixes can be distinguished.
    """
    logger.debug(
        "op=review_threads_page pr=%d page=%d cursor_in=%s end_cursor=%s "
        "nodes=%d cumulative=%d has_next=%s",
        pull_request, pages_seen,
        cursor if cursor else "<start>",
        page_info.get("endCursor"),
        len(page_nodes), aggregated_count,
        bool(page_info.get("hasNextPage")),
    )


def _warn_review_threads_capped(pull_request: int, aggregated_count: int) -> None:
    """Emit cap-truncation warning. The PR #1887 retro names silent
    truncation as the false-zero failure class; the warning is the
    machine-readable signal that the result is a lower bound, not exact.
    """
    warnings.warn(
        f"Hit _REVIEW_THREADS_MAX_PAGES={_REVIEW_THREADS_MAX_PAGES} for "
        f"PR #{pull_request}; result truncated at {aggregated_count} "
        f"threads. Unresolved-thread count is a lower bound, not exact.",
        stacklevel=3,
    )


def _warn_structural_truncation(
    owner: str, repo: str, pull_request: int, pages_seen: int, aggregated_count: int,
) -> None:
    """Surface a mid-pagination structural failure.

    Mid-pagination structural failure: pages 1..N-1 succeeded and page N
    returned a structurally invalid response. The callers see a truncated
    result, so emit the same surfaced warning shape used for cursor_missing
    and page-cap-exceeded rather than letting the empty-page silently
    terminate the loop. Page 1 failures already return [] in the caller; this
    guard is the multi-page case.
    """
    warnings.warn(
        f"Mid-pagination structural failure for PR "
        f"#{pull_request} on page {pages_seen}; result truncated "
        f"at {aggregated_count} threads. Reason: structural_failure.",
        stacklevel=2,
    )
    _log_structural_missing(
        owner, repo, pull_request, pages_seen, aggregated_count, "structural_failure",
    )


def _warn_cursor_missing(
    owner: str, repo: str, pull_request: int, pages_seen: int, aggregated_count: int,
) -> None:
    """Surface a hasNextPage=true with empty/null endCursor.

    Cannot advance, so surface as a truncation event rather than a clean exit,
    since callers would otherwise see a "complete"-looking result that
    silently dropped pages 2+.
    """
    warnings.warn(
        f"hasNextPage=true but endCursor empty for PR "
        f"#{pull_request} on page {pages_seen}; result truncated "
        f"at {aggregated_count} threads. Reason: cursor_missing.",
        stacklevel=2,
    )
    _log_structural_missing(
        owner, repo, pull_request, pages_seen, aggregated_count, "cursor_missing",
    )


def get_unresolved_review_threads(
    owner: str,
    repo: str,
    pull_request: int,
) -> list[dict]:
    """Retrieve unresolved review threads on a pull request.

    Pages through reviewThreads until ``pageInfo.hasNextPage`` is false or
    ``_REVIEW_THREADS_MAX_PAGES`` is reached. Returns ``[]`` on transport
    failure (never raises, never partial). On a cap-hit or mid-pagination
    truncation, returns whatever was collected and emits ``warnings.warn``.
    Closes the PR #1887 silent-truncation failure modes.
    """
    op_start = time.monotonic()
    aggregated: list[dict] = []
    cursor: str | None = None
    pages_seen = 0

    while pages_seen < _REVIEW_THREADS_MAX_PAGES:
        pages_seen += 1
        status, review_threads = _fetch_review_threads_page(
            owner, repo, pull_request, cursor, pages_seen, len(aggregated),
        )
        if status == FetchStatus.TRANSPORT_ERROR:
            return []
        if status == FetchStatus.STRUCTURAL_MISSING:
            if pages_seen > 1:
                _warn_structural_truncation(
                    owner, repo, pull_request, pages_seen, len(aggregated),
                )
            break
        assert review_threads is not None  # noqa: S101
        page_nodes = review_threads.get("nodes", [])
        aggregated.extend(page_nodes)

        page_info = review_threads.get("pageInfo") or {}
        _log_review_threads_page(
            pull_request, pages_seen, cursor, page_info,
            page_nodes, len(aggregated),
        )
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            _warn_cursor_missing(
                owner, repo, pull_request, pages_seen, len(aggregated),
            )
            break
    else:
        _warn_review_threads_capped(pull_request, len(aggregated))

    unresolved = filter_unresolved_threads(aggregated)
    logger.info(
        "op=review_threads_complete pr=%d owner=%s repo=%s "
        "pages=%d total=%d unresolved=%d duration_ms=%d",
        pull_request, owner, repo, pages_seen,
        len(aggregated), len(unresolved),
        int((time.monotonic() - op_start) * 1000),
    )
    return unresolved
