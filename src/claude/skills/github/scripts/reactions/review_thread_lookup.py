"""Parse paginated review thread lookup responses."""

from __future__ import annotations

from typing import Any

REVIEW_THREADS_QUERY = """\
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


def review_threads_page(
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


def thread_with_root_comment(
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
